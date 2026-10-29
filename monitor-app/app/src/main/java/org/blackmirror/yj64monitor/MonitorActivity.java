package org.blackmirror.yj64monitor;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class MonitorActivity extends Activity {
    private static final String TARGET_PACKAGE = "org.blackmirror.blackmirror";
    private static final String OWNER = "concreteballs";
    private static final String REPO = "yj64-clean-bial2modFun";
    private static final String BRANCH = "main";
    private static final String REPORT_PATH = "yj64-reports/yj64-report.jsonl";
    private static final String KEY_ALIAS = "yj64_standalone_monitor_github_key";
    private static final String TOKEN_FILE = "yj64-github-token.enc";
    private TextView status;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        appendEvent("monitor_started", "{\"package\":\"" + TARGET_PACKAGE + "\"}");
        buildUi();
        refreshDiagnostics();
        autoUploadReportIfConfigured();
    }

    private void autoUploadReportIfConfigured() {
        if (!tokenFile().isFile()) return;
        appendEvent("diagnostic_report_auto_upload_started",
            "{\"trigger\":\"monitor_opened\",\"repository\":\"" + OWNER + "/" + REPO + "\",\"branch\":\"" + BRANCH + "\",\"path\":\"Report\"}");
        uploadReport();
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(28, 24, 28, 24);

        TextView title = new TextView(this);
        title.setText("YJ-64 Monitor");
        title.setTextSize(26);
        title.setPadding(0, 0, 0, 12);
        root.addView(title, new LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT));

        status = new TextView(this);
        status.setTextSize(14);
        status.setTextIsSelectable(true);
        root.addView(status, new LinearLayout.LayoutParams(-1, 0, 1));

        addButton(root, "LAUNCH YJ-64", v -> launchBase());
        addButton(root, "REFRESH CRASH REPORT", v -> refreshDiagnostics());
        addButton(root, "COPY DIAGNOSTIC REPORT", v -> copyReport());
        addButton(root, "CONFIGURE GITHUB UPLOAD", v -> configureToken());
        addButton(root, "UPLOAD REPORT TO GITHUB", v -> confirmUpload());

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root);
        setContentView(scroll);
    }

    private void addButton(LinearLayout root, String text, android.view.View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(text);
        button.setOnClickListener(listener);
        root.addView(button, new LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT));
    }

    private File reportFile() {
        File dir = new File(getFilesDir(), "yj64-reports");
        if (!dir.exists()) dir.mkdirs();
        return new File(dir, "yj64-report.jsonl");
    }

    private void appendEvent(String event, String dataJson) {
        JSONObject row = new JSONObject();
        try {
            row.put("schema", "yj64.diagnostic.v1");
            row.put("agent", "yj64-standalone-monitor");
            row.put("event", event);
            row.put("timestamp_ms", System.currentTimeMillis());
            row.put("report_id", UUID.randomUUID().toString().replace("-", ""));
            row.put("data", new JSONObject(dataJson));
            try (FileOutputStream out = new FileOutputStream(reportFile(), true)) {
                out.write((row.toString() + "\n").getBytes(StandardCharsets.UTF_8));
                out.getFD().sync();
            }
        } catch (Exception ignored) { }
    }

    private String readReport() {
        File file = reportFile();
        StringBuilder result = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) result.append(line).append('\n');
        } catch (Exception e) {
            return "Report read failed: " + e.getClass().getSimpleName();
        }
        return result.toString();
    }

    private void launchBase() {
        appendEvent("base_launch_requested", "{\"target_package\":\"" + TARGET_PACKAGE + "\"}");
        try {
            Intent intent = getPackageManager().getLaunchIntentForPackage(TARGET_PACKAGE);
            if (intent == null) {
                appendEvent("base_launch_failed", "{\"reason\":\"package_not_installed_or_not_visible\"}");
                status.setText("YJ-64 is not installed or Android did not expose its launch activity.\n\n" + reportSummary());
                Toast.makeText(this, "YJ-64 launch activity not found", Toast.LENGTH_LONG).show();
                return;
            }
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
            appendEvent("base_launch_activity_started", "{\"success\":true}");
            status.setText("Launch request sent to YJ-64. Return here after a crash and press REFRESH CRASH REPORT.\n\n" + reportSummary());
        } catch (Exception e) {
            appendEvent("base_launch_failed", "{\"error_type\":\"" + esc(e.getClass().getSimpleName()) + "\",\"message\":\"" + esc(String.valueOf(e.getMessage())) + "\"}");
            status.setText("Launch failed: " + e.getClass().getSimpleName() + "\n\n" + reportSummary());
        }
    }

    private String reportSummary() {
        return "Monitor report: " + reportFile().getAbsolutePath()
                + "\nTarget package: " + TARGET_PACKAGE
                + "\nGitHub destination: " + OWNER + "/" + REPO + "/" + "Report";
    }

    private void refreshDiagnostics() {
        StringBuilder text = new StringBuilder();
        text.append("MONITOR ALIVE\nPackage: ").append(getPackageName())
            .append("\nPID: ").append(android.os.Process.myPid())
            .append("\n\n").append(reportSummary()).append("\n\n");
        appendEvent("crash_check_started", "{\"target_package\":\"" + TARGET_PACKAGE + "\"}");

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                ActivityManager manager = (ActivityManager) getSystemService(ACTIVITY_SERVICE);
                List<ApplicationExitInfo> exits = manager.getHistoricalProcessExitReasons(TARGET_PACKAGE, 0, 10);
                text.append("Recent target process exits (newest first):\n");
                if (exits == null || exits.isEmpty()) {
                    text.append("No Android process-exit records are available yet.\n");
                    appendEvent("crash_check_no_records", "{\"target_package\":\"" + TARGET_PACKAGE + "\"}");
                } else {
                    JSONArray found = new JSONArray();
                    for (ApplicationExitInfo info : exits) {
                        JSONObject item = new JSONObject();
                        item.put("timestamp_ms", info.getTimestamp());
                        item.put("reason_code", info.getReason());
                        item.put("reason", reasonName(info.getReason()));
                        item.put("status", info.getStatus());
                        item.put("importance", info.getImportance());
                        item.put("process_name", info.getProcessName());
                        item.put("description", String.valueOf(info.getDescription()));
                        found.put(item);
                        text.append("\n• ").append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US)
                                .format(new Date(info.getTimestamp())))
                            .append(" — ").append(reasonName(info.getReason()))
                            .append(" (status ").append(info.getStatus()).append(")")
                            .append("\n  Process: ").append(info.getProcessName())
                            .append("\n  ").append(info.getDescription()).append("\n");
                        String trace = readTrace(info);
                        if (!trace.isEmpty()) {
                            text.append("  Trace excerpt:\n").append(trace).append("\n");
                            item.put("trace_excerpt", trace);
                        }
                    }
                    appendEvent("target_process_exits_collected", new JSONObject()
                        .put("target_package", TARGET_PACKAGE).put("exits", found).toString());
                }
            } catch (SecurityException e) {
                text.append("Android does not allow this monitor to read another app's historical process exits. ")
                    .append("This is an expected platform restriction, not evidence that YJ-64 Base crashed.\n")
                    .append("Using Base-side diagnostic IPC instead.\n");
                JSONObject unavailable = new JSONObject();
                try {
                    unavailable.put("error_type", e.getClass().getName());
                    unavailable.put("message", String.valueOf(e.getMessage()));
                    unavailable.put("target_package", TARGET_PACKAGE);
                    unavailable.put("monitor_package", getPackageName());
                    unavailable.put("android_api", Build.VERSION.SDK_INT);
                    unavailable.put("android_release", Build.VERSION.RELEASE);
                    unavailable.put("diagnostic_api", "ActivityManager.getHistoricalProcessExitReasons");
                    unavailable.put("cross_application_query", true);
                    unavailable.put("base_side_ipc_expected", true);
                } catch (Exception ignored) { }
                appendEvent("cross_app_exit_history_unavailable", unavailable.toString());
            } catch (Exception e) {
                String stack = stackTrace(e);
                String message = String.valueOf(e.getMessage());
                text.append("Crash history read failed: ").append(e.getClass().getSimpleName())
                    .append("\nMessage: ").append(message)
                    .append("\nAndroid API: ").append(Build.VERSION.SDK_INT)
                    .append("\nTarget package: ").append(TARGET_PACKAGE)
                    .append("\n\nStack trace:\n").append(stack).append("\n");
                JSONObject failure = new JSONObject();
                try {
                    failure.put("error_type", e.getClass().getName());
                    failure.put("message", message);
                    failure.put("stack_trace", stack);
                    failure.put("target_package", TARGET_PACKAGE);
                    failure.put("monitor_package", getPackageName());
                    failure.put("android_api", Build.VERSION.SDK_INT);
                    failure.put("android_release", Build.VERSION.RELEASE);
                    failure.put("diagnostic_api", "ActivityManager.getHistoricalProcessExitReasons");
                    failure.put("cross_application_query", true);
                    failure.put("dump_permission_hint", false);
                } catch (Exception ignored) { }
                appendEvent("crash_check_failed", failure.toString());
            }
        } else {
            text.append("Android 11+ is required for historical process exit diagnostics.\n");
        }
        status.setText(text.toString());
    }

    private String readTrace(ApplicationExitInfo info) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return "";
        try (InputStream input = info.getTraceInputStream()) {
            if (input == null) return "";
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[2048];
            int count;
            while ((count = input.read(buffer)) != -1 && output.size() < 16000) output.write(buffer, 0, count);
            return new String(output.toByteArray(), StandardCharsets.UTF_8);
        } catch (Exception e) {
            JSONObject failure = new JSONObject();
            try {
                failure.put("error_type", e.getClass().getName());
                failure.put("message", String.valueOf(e.getMessage()));
                failure.put("stack_trace", stackTrace(e));
                failure.put("target_package", TARGET_PACKAGE);
            } catch (Exception ignored) { }
            appendEvent("target_trace_read_failed", failure.toString());
            return "";
        }
    }

    private String stackTrace(Throwable error) {
        StringWriter buffer = new StringWriter();
        PrintWriter writer = new PrintWriter(buffer);
        error.printStackTrace(writer);
        writer.flush();
        String value = buffer.toString();
        return value.length() > 12000 ? value.substring(0, 12000) : value;
    }

    private String reasonName(int reason) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            switch (reason) {
                case ApplicationExitInfo.REASON_CRASH: return "CRASH";
                case ApplicationExitInfo.REASON_CRASH_NATIVE: return "NATIVE_CRASH";
                case ApplicationExitInfo.REASON_ANR: return "ANR";
                case ApplicationExitInfo.REASON_LOW_MEMORY: return "LOW_MEMORY";
                case ApplicationExitInfo.REASON_SIGNALED: return "SIGNALED";
                case ApplicationExitInfo.REASON_EXIT_SELF: return "EXIT_SELF";
                case ApplicationExitInfo.REASON_DEPENDENCY_DIED: return "DEPENDENCY_DIED";
                case ApplicationExitInfo.REASON_INITIALIZATION_FAILURE: return "INITIALIZATION_FAILURE";
                case ApplicationExitInfo.REASON_PERMISSION_CHANGE: return "PERMISSION_CHANGE";
                case ApplicationExitInfo.REASON_EXCESSIVE_RESOURCE_USAGE: return "EXCESSIVE_RESOURCE_USAGE";
                case ApplicationExitInfo.REASON_USER_REQUESTED: return "USER_REQUESTED";
                case ApplicationExitInfo.REASON_USER_STOPPED: return "USER_STOPPED";
                case ApplicationExitInfo.REASON_OTHER: return "OTHER";
                default: return "REASON_" + reason;
            }
        }
        return "REASON_" + reason;
    }

    private void copyReport() {
        String report = readReport();
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        clipboard.setPrimaryClip(ClipData.newPlainText("YJ-64 diagnostic report", report));
        Toast.makeText(this, "Diagnostic report copied", Toast.LENGTH_LONG).show();
        appendEvent("diagnostic_report_copied", "{\"characters\":" + report.length() + "}");
    }

    private SecretKey encryptionKey() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) return (SecretKey) store.getKey(KEY_ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build());
        return generator.generateKey();
    }

    private File tokenFile() { return new File(getFilesDir(), TOKEN_FILE); }

    private void saveToken(String token) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, encryptionKey());
        byte[] encrypted = cipher.doFinal(token.trim().getBytes(StandardCharsets.UTF_8));
        byte[] iv = cipher.getIV();
        byte[] combined = new byte[iv.length + encrypted.length];
        System.arraycopy(iv, 0, combined, 0, iv.length);
        System.arraycopy(encrypted, 0, combined, iv.length, encrypted.length);
        try (FileOutputStream out = new FileOutputStream(tokenFile(), false)) {
            out.write(Base64.encode(combined, Base64.NO_WRAP));
            out.getFD().sync();
        }
    }

    private String loadToken() throws Exception {
        if (!tokenFile().isFile()) return "";
        byte[] combined = Base64.decode(readAll(tokenFile()), Base64.NO_WRAP);
        if (combined.length <= 12) throw new IllegalStateException("stored token invalid");
        byte[] iv = java.util.Arrays.copyOfRange(combined, 0, 12);
        byte[] encrypted = java.util.Arrays.copyOfRange(combined, 12, combined.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, encryptionKey(), new GCMParameterSpec(128, iv));
        return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
    }

    private String readAll(File file) throws Exception {
        try (FileInputStream in = new FileInputStream(file); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096]; int count;
            while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        }
    }

    private void configureToken() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
        input.setHint("Fine-grained GitHub token");
        new AlertDialog.Builder(this).setTitle("GitHub report upload")
            .setMessage("Create a fine-grained token limited to " + OWNER + "/" + REPO + " with Contents: Read and write. The complete diagnostic JSONL will be uploaded automatically whenever this monitor opens to the PUBLIC Report file on branch " + BRANCH + ". Reports can include crash details. Saving the token enables that publishing behavior. The token is encrypted with Android Keystore and is not embedded in this APK.")
            .setView(input).setNegativeButton("CANCEL", (d, w) -> d.dismiss())
            .setPositiveButton("SAVE TOKEN", (d, w) -> {
                String token = input.getText().toString().trim();
                if (token.isEmpty()) return;
                try {
                    saveToken(token);
                    appendEvent("github_report_token_saved", "{\"encrypted\":true}");
                    Toast.makeText(this, "Token saved securely on this device", Toast.LENGTH_LONG).show();
                } catch (Exception e) {
                    Toast.makeText(this, "Token save failed: " + e.getClass().getSimpleName(), Toast.LENGTH_LONG).show();
                }
            }).show();
    }

    private void confirmUpload() {
        new AlertDialog.Builder(this).setTitle("Upload diagnostic report?")
            .setMessage("The complete diagnostic report will be uploaded to the PUBLIC repository " + OWNER + "/" + REPO + " at Report. It may contain system crash details. Continue only if you agree to publish it.")
            .setNegativeButton("CANCEL", (d, w) -> d.dismiss())
            .setPositiveButton("UPLOAD", (d, w) -> uploadReport()).show();
    }

    private void uploadReport() {
        final String token;
        try { token = loadToken(); }
        catch (Exception e) {
            Toast.makeText(this, "Could not decrypt token; configure it again", Toast.LENGTH_LONG).show();
            configureToken();
            return;
        }
        if (token.isEmpty()) {
            Toast.makeText(this, "Configure a GitHub token first", Toast.LENGTH_LONG).show();
            configureToken();
            return;
        }
        appendEvent("diagnostic_report_upload_started", "{\"destination\":\"" + OWNER + "/" + REPO + "/blob/" + BRANCH + "/Report\"}");
        final String content = readReport();
        status.setText("Uploading diagnostic report to GitHub...");
        new Thread(() -> {
            HttpURLConnection connection = null;
            try {
                String api = "https://api.github.com/repos/" + OWNER + "/" + REPO + "/contents/Report";
                String existingSha = "";
                HttpURLConnection lookup = (HttpURLConnection) new URL(api + "?ref=" + BRANCH).openConnection();
                lookup.setRequestMethod("GET");
                lookup.setConnectTimeout(15000);
                lookup.setReadTimeout(20000);
                lookup.setRequestProperty("Authorization", "Bearer " + token);
                lookup.setRequestProperty("Accept", "application/vnd.github+json");
                lookup.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
                int lookupCode = lookup.getResponseCode();
                if (lookupCode == 200) existingSha = new JSONObject(readStream(lookup.getInputStream())).optString("sha", "");
                else if (lookupCode != 404) throw new IllegalStateException("GitHub lookup HTTP " + lookupCode);
                lookup.disconnect();

                JSONObject payload = new JSONObject();
                payload.put("message", "Update YJ-64 standalone monitor diagnostic report");
                payload.put("content", Base64.encodeToString(content.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP));
                payload.put("branch", BRANCH);
                if (!existingSha.isEmpty()) payload.put("sha", existingSha);

                int code = 0;
                String response = "";
                for (int attempt = 0; attempt < 2; attempt++) {
                    connection = (HttpURLConnection) new URL(api).openConnection();
                    connection.setRequestMethod("PUT");
                    connection.setConnectTimeout(15000);
                    connection.setReadTimeout(30000);
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Authorization", "Bearer " + token);
                    connection.setRequestProperty("Accept", "application/vnd.github+json");
                    connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
                    connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    try (OutputStream out = connection.getOutputStream()) {
                        out.write(payload.toString().getBytes(StandardCharsets.UTF_8));
                        out.flush();
                    }
                    code = connection.getResponseCode();
                    InputStream responseStream = code >= 200 && code < 400
                        ? connection.getInputStream() : connection.getErrorStream();
                    response = readStream(responseStream);
                    if (code == 429 && attempt == 0) {
                        appendEvent("github_report_rate_limited",
                            "{\"http_status\":429,\"retry_after_seconds\":45,\"retry_count\":1}");
                        connection.disconnect();
                        connection = null;
                        Thread.sleep(45000L);
                        continue;
                    }
                    break;
                }
                if (code < 200 || code >= 300) throw new IllegalStateException("GitHub upload HTTP " + code + ": " + response);
                JSONObject json = new JSONObject(response);
                String htmlUrl = json.optJSONObject("content") == null ? "" : json.optJSONObject("content").optString("html_url", "");
                appendEvent("diagnostic_report_uploaded", "{\"success\":true,\"http_status\":" + code + ",\"bytes\":" + content.getBytes(StandardCharsets.UTF_8).length + ",\"url\":\"" + esc(htmlUrl) + "\"}");
                runOnUiThread(() -> {
                    status.setText("Report uploaded successfully.\n" + htmlUrl + "\n\n" + reportSummary());
                    Toast.makeText(this, "Report uploaded to GitHub", Toast.LENGTH_LONG).show();
                });
            } catch (Exception e) {
                appendEvent("diagnostic_report_upload_failed", "{\"error_type\":\"" + esc(e.getClass().getSimpleName()) + "\",\"message\":\"" + esc(String.valueOf(e.getMessage())) + "\"}");
                runOnUiThread(() -> {
                    status.setText("Report upload failed: " + e.getMessage() + "\n\n" + reportSummary());
                    Toast.makeText(this, "GitHub upload failed", Toast.LENGTH_LONG).show();
                });
            } finally {
                if (connection != null) connection.disconnect();
            }
        }).start();
    }

    private String readStream(InputStream stream) throws Exception {
        if (stream == null) return "";
        try (InputStream in = stream; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096]; int count;
            while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        }
    }

    private String esc(String value) {
        if (value == null) return "";
        return value.replace("\\", "\\\\").replace("\"", "\\\"")
            .replace("\n", "\\n").replace("\r", "\\r");
    }
}
