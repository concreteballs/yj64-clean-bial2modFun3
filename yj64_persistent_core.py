"""Persistent event ledger and verified cumulative YJ-64 archive."""
from __future__ import annotations
import hashlib, json, os, re, shutil, sqlite3, time, uuid, zipfile
from pathlib import Path, PurePosixPath
from typing import Any

class PersistentCore:
    ARCHIVE_SCHEMA = "yj64.archive.v2"
    SECRET_KEYS = {"private_messages","api_key","api_keys","token","access_token","refresh_token","authorization"}
    def __init__(self,user_data_dir:str|Path):
        self.root=Path(user_data_dir);self.root.mkdir(parents=True,exist_ok=True)
        self.db_path=self.root/"yj64-persistent-core.sqlite3";self.workspace_path=self.root/"yj64-workspace"
        self.report_path=self.root/"yj64-reports"/"yj64-report.jsonl";self.archive_state_path=self.root/"yj64-archive-state.zip"
        with self._connect() as db:db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_ms INTEGER NOT NULL, event TEXT NOT NULL, data_json TEXT NOT NULL)")
    def _connect(self):
        db=sqlite3.connect(str(self.db_path),timeout=5);db.execute("PRAGMA journal_mode=WAL");return db
    def record_event(self,event:str,data:dict[str,Any]|None=None)->None:
        try:
            with self._connect() as db:db.execute("INSERT INTO events(timestamp_ms,event,data_json) VALUES(?,?,?)",(int(time.time()*1000),str(event),json.dumps(data or {},ensure_ascii=False)))
        except sqlite3.Error:return
    @staticmethod
    def _sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
    @staticmethod
    def _safe_name(name:str)->bool:
        p=PurePosixPath(name);return bool(name) and not p.is_absolute() and all(x not in ("",".","..") for x in p.parts) and "\\" not in name
    @classmethod
    def _sanitize(cls,value:Any)->Any:
        if isinstance(value,dict):return {k:cls._sanitize(v) for k,v in value.items() if str(k).lower() not in cls.SECRET_KEYS}
        if isinstance(value,list):return [cls._sanitize(x) for x in value]
        return value
    @classmethod
    def _sanitize_json(cls,payload:bytes)->bytes:
        try:data=json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError):return payload
        return json.dumps(cls._sanitize(data),ensure_ascii=False,indent=2).encode("utf-8")
    def _collect_files(self)->dict[str,bytes]:
        result={}
        for base in (self.workspace_path,self.report_path):
            if base.is_file() and not base.is_symlink():items=[base]
            elif base.is_dir() and not base.is_symlink():items=[p for p in base.rglob("*") if p.is_file() and not p.is_symlink()]
            else:items=[]
            for p in items:
                name=p.relative_to(self.root).as_posix();data=p.read_bytes()
                result[name]=self._sanitize_json(data) if p.suffix.lower()==".json" else data
        for pattern in ("yj64-router-config.json","yj64-llm-config*.json"):
            for p in self.root.glob(pattern):
                if p.is_file() and not p.is_symlink():result[p.name]=self._sanitize_json(p.read_bytes())
        return result
    @staticmethod
    def _merge_history(old:bytes,new:bytes)->bytes:
        try:a=json.loads(old.decode("utf-8"));b=json.loads(new.decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError):return new
        if not isinstance(a,list) or not isinstance(b,list):return new
        merged={}
        for item in a+b:
            if not isinstance(item,dict):continue
            mid=str(item.get("message_id") or "legacy:"+hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest());merged[mid]=item
        rows=list(merged.values());rows.sort(key=lambda x:(x.get("timestamp",x.get("timestamp_ms",0)) or 0,str(x.get("message_id",""))))
        return json.dumps(rows,ensure_ascii=False,indent=2).encode("utf-8")
    def _read_previous(self):
        if not self.archive_state_path.is_file() or not zipfile.is_zipfile(self.archive_state_path):return {},None
        try:
            with zipfile.ZipFile(self.archive_state_path) as z:
                if z.testzip():return {},None
                m=json.loads(z.read("manifest.json").decode("utf-8"))
                if m.get("schema")!=self.ARCHIVE_SCHEMA:return {},None
                return {n:z.read(n) for n in m.get("files",{})},m
        except (OSError,KeyError,ValueError,zipfile.BadZipFile,json.JSONDecodeError):return {},None
    def export_archive(self,destination:str|Path)->Path:
        dest=Path(destination);dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_suffix(dest.suffix+".tmp");state_tmp=self.archive_state_path.with_suffix(".zip.tmp")
        previous,old_manifest=self._read_previous();merged=dict(previous);current=self._collect_files()
        for name,data in current.items():
            if name.startswith("yj64-workspace/chats/") and name.endswith(".json") and name in merged:data=self._merge_history(merged[name],data)
            merged[name]=data
        idx="yj64-workspace/chats.json"
        if idx not in merged:raise IOError("Archive cannot be created: chat index missing")
        try:index=json.loads(merged[idx].decode("utf-8"));chats=index.get("chats",[]) if isinstance(index,dict) else []
        except (UnicodeDecodeError,json.JSONDecodeError,AttributeError) as exc:raise IOError("Invalid archive chat index") from exc
        if not isinstance(chats,list) or not chats:raise IOError("Archive has no saved chats")
        for item in chats:
            cid=re.sub(r"[^A-Za-z0-9_-]","",str(item.get("id",""))) if isinstance(item,dict) else ""
            if not cid or f"yj64-workspace/chats/{cid}.json" not in merged:raise IOError("Saved chat history missing")
        try:
            with self._connect() as db:events=db.execute("SELECT timestamp_ms,event,data_json FROM events ORDER BY id").fetchall()
            merged["yj64-events-export.json"]=json.dumps(events,ensure_ascii=False).encode("utf-8")
        except sqlite3.Error:pass
        messages=[]
        for name,data in merged.items():
            if name.startswith("yj64-workspace/chats/") and name.endswith(".json"):
                rows=json.loads(data.decode("utf-8"))
                if isinstance(rows,list):messages.extend(x for x in rows if isinstance(x,dict))
        messages.sort(key=lambda x:x.get("timestamp",x.get("timestamp_ms",0)) or 0);now=int(time.time()*1000)
        manifest={"schema":self.ARCHIVE_SCHEMA,"archive_id":(old_manifest or {}).get("archive_id") or uuid.uuid4().hex,
          "created_at":(old_manifest or {}).get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(now/1000)),
          "updated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(now/1000)),
          "last_message_id":str(messages[-1].get("message_id","")) if messages else None,"message_count":len(messages),
          "included":["common_chat_history","workspace_metadata","local_skills","router_model_settings_without_secrets","technical_diagnostics"],
          "excluded":["participant_private_messages","api_keys_and_tokens","application_private_database"],
          "files":{n:{"sha256":self._sha(d),"size":len(d)} for n,d in sorted(merged.items())}}
        try:
            for target in (tmp,state_tmp):
                with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED) as z:
                    for n,d in sorted(merged.items()):z.writestr(n,d)
                    z.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2))
                self._verify_archive(target)
            os.replace(state_tmp,self.archive_state_path);os.replace(tmp,dest)
        except Exception:tmp.unlink(missing_ok=True);state_tmp.unlink(missing_ok=True);raise
        return dest
    def _verify_archive(self,path:Path):
        if not path.is_file() or path.stat().st_size<=0 or not zipfile.is_zipfile(path):raise IOError("Archive ZIP empty or invalid")
        with zipfile.ZipFile(path) as z:
            names=z.namelist()
            if z.testzip() or len(names)!=len(set(names)) or names.count("manifest.json")!=1:raise IOError("Archive integrity/manifest check failed")
            m=json.loads(z.read("manifest.json").decode("utf-8"))
            if m.get("schema")!=self.ARCHIVE_SCHEMA or not isinstance(m.get("files"),dict):raise IOError("Unsupported archive manifest")
            for n,meta in m["files"].items():
                if not self._safe_name(n) or n not in names:raise IOError("Unsafe or missing archive path")
                data=z.read(n)
                if len(data)!=int(meta.get("size",-1)) or self._sha(data)!=meta.get("sha256"):raise IOError("Archive SHA-256/size mismatch: "+n)
            if set(names)!=set(m["files"])|{"manifest.json"}:raise IOError("Undeclared archive files")
            return m
    def import_archive(self,source:str|Path)->int:
        source=Path(source)
        if not source.is_file() or not zipfile.is_zipfile(source):raise ValueError("Not a valid ZIP archive")
        with zipfile.ZipFile(source) as z:
            names=z.namelist()
            if z.testzip() or len(names)!=len(set(names)) or names.count("manifest.json")!=1:raise ValueError("Archive integrity/manifest check failed")
            m=json.loads(z.read("manifest.json").decode("utf-8"));schema=m.get("schema") if isinstance(m,dict) else None
            if schema not in ("yj64.archive.v1",self.ARCHIVE_SCHEMA):raise ValueError("Unsupported archive schema")
            declared=m.get("files")
            if schema==self.ARCHIVE_SCHEMA:
                if not isinstance(declared,dict):raise ValueError("Invalid hash manifest")
                payloads={}
                for n,meta in declared.items():
                    if not self._safe_name(n) or n not in names:raise ValueError("Unsafe/missing archive path")
                    data=z.read(n)
                    if len(data)!=int(meta.get("size",-1)) or self._sha(data)!=meta.get("sha256"):raise ValueError("Archive SHA-256/size mismatch: "+n)
                    payloads[n]=data
                if set(names)!=set(payloads)|{"manifest.json"}:raise ValueError("Undeclared archive files")
            else:
                if not isinstance(declared,list) or not all(isinstance(n,str) and self._safe_name(n) for n in declared):raise ValueError("Invalid legacy manifest")
                payloads={n:z.read(n) for n in declared if n in names}
                if set(payloads)!=set(declared):raise ValueError("Legacy archive contents mismatch")
        idx="yj64-workspace/chats.json"
        if idx not in payloads:raise ValueError("Archive chat index missing")
        index=json.loads(payloads[idx].decode("utf-8"));chats=index.get("chats",[]) if isinstance(index,dict) else []
        if not isinstance(chats,list) or not chats:raise ValueError("Archive has no saved chats")
        for item in chats:
            cid=re.sub(r"[^A-Za-z0-9_-]","",str(item.get("id",""))) if isinstance(item,dict) else "";h=f"yj64-workspace/chats/{cid}.json"
            if not cid or h not in payloads:raise ValueError("Archive chat history missing")
            rows=json.loads(payloads[h].decode("utf-8"))
            if not isinstance(rows,list) or not all(isinstance(x,dict) and "role" in x and "content" in x for x in rows):raise ValueError("Invalid chat history")
        staged=[];allowed_root={"yj64-router-config.json"}
        try:
            for n,data in payloads.items():
                allowed=n.startswith(("yj64-workspace/","yj64-reports/")) or n in allowed_root or (n.startswith("yj64-llm-config-") and n.endswith(".json"))
                if not allowed:continue
                target=self.root/n;target.parent.mkdir(parents=True,exist_ok=True);stage=target.with_name(target.name+".restore-tmp");stage.write_bytes(data)
                backup=target.read_bytes() if target.is_file() else None;staged.append((target,stage,backup))
            committed=[]
            try:
                for target,stage,backup in staged:os.replace(stage,target);committed.append((target,backup))
            except Exception:
                for target,backup in reversed(committed):
                    if backup is None:target.unlink(missing_ok=True)
                    else:
                        rollback=target.with_name(target.name+".rollback-tmp");rollback.write_bytes(backup);os.replace(rollback,target)
                raise
        finally:
            for _,stage,_ in staged:stage.unlink(missing_ok=True)
        if schema==self.ARCHIVE_SCHEMA:
            state_tmp=self.archive_state_path.with_suffix(".zip.tmp");shutil.copyfile(source,state_tmp);os.replace(state_tmp,self.archive_state_path)
        return len(staged)
