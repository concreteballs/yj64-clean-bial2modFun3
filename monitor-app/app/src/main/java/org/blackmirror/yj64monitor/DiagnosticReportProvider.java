package org.blackmirror.yj64monitor;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.os.Binder;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

public class DiagnosticReportProvider extends ContentProvider {
    @Override public boolean onCreate() {
        return true;
    }

    @Override public Bundle call(String method, String arg, Bundle extras) {
        Bundle result = new Bundle();
        if (!"receive_report".equals(method)) {
            result.putBoolean("ok", false);
            result.putString("error", "unsupported_method");
            return result;
        }

        String reportId = "";
        try {
            int callingUid = Binder.getCallingUid();
            String[] callerPackages = getContext().getPackageManager()
                .getPackagesForUid(callingUid);
            boolean allowedCaller = false;
            if (callerPackages != null) {
                for (String callerPackage : callerPackages) {
                    if ("org.blackmirror.blackmirror".equals(callerPackage)) {
                        allowedCaller = true;
                        break;
                    }
                }
            }
            if (!allowedCaller) {
                throw new SecurityException("caller_package_not_allowed");
            }
            if (extras == null) throw new IllegalArgumentException("extras_missing");
            String raw = extras.getString("report_json");
            if (raw == null || raw.length() > 131072) {
                throw new IllegalArgumentException("report_missing_or_oversized");
            }
            JSONObject report = new JSONObject(raw);
            reportId = report.optString("report_id",
                report.optString("message_id", ""));
            if (reportId.isEmpty()) throw new IllegalArgumentException("report_id_missing");
            report.put("_external_monitor_received_at_ms", System.currentTimeMillis());
            report.put("_external_monitor_source_package", "org.blackmirror.blackmirror");

            File directory = new File(getContext().getFilesDir(), "yj64-reports");
            if (!directory.exists() && !directory.mkdirs()) {
                throw new IllegalStateException("report_directory_unavailable");
            }
            File file = new File(directory, "yj64-report.jsonl");
            try (FileOutputStream out = new FileOutputStream(file, true)) {
                out.write((report.toString() + "\n").getBytes(StandardCharsets.UTF_8));
                out.flush();
                out.getFD().sync();
            }
            result.putBoolean("ok", true);
            result.putString("report_id", reportId);
        } catch (Exception error) {
            result.putBoolean("ok", false);
            result.putString("report_id", reportId);
            result.putString("error_type", error.getClass().getName());
            result.putString("error", String.valueOf(error.getMessage()));
        }
        return result;
    }

    @Override public Cursor query(Uri uri, String[] projection, String selection,
                                  String[] selectionArgs, String sortOrder) {
        return null;
    }

    @Override public String getType(Uri uri) {
        return null;
    }

    @Override public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override public int delete(Uri uri, String selection, String[] selectionArgs) {
        return 0;
    }

    @Override public int update(Uri uri, ContentValues values, String selection,
                                String[] selectionArgs) {
        return 0;
    }
}
