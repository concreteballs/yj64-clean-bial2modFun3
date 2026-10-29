package org.blackmirror.blackmirror;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Bundle;
import android.os.Process;
import android.view.ViewGroup;
import android.text.InputType;
import android.util.Base64;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.security.KeyStore;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

public class MonitorActivity extends Activity {
    private static final String REPORT = "yj64-reports/yj64-report.jsonl";
    private static final String PID_FILE = "yj64-main-process.pid";
    private TextView status;
    private static final int PICK_CONFIG_FILE = 4101;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        append("monitor_window_opened", identityJson());

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 32, 32, 32);

        TextView title = new TextView(this);
        title.setText("YJ-64 Internal Monitor");
        title.setTextSize(24);
        root.addView(title, new LinearLayout.LayoutParams(-1, 80));

        status = new TextView(this);
        status.setText(identityText());
        status.setTextIsSelectable(true);
        root.addView(status, new LinearLayout.LayoutParams(-1, 0, 1));

        Button config = new Button(this);
        config.setText("Import LLM config file");
        config.setOnClickListener(v -> pickConfigFile());
        root.addView(config);

        Button refresh = new Button(this);
        refresh.setText("Refresh monitor status");
        refresh.setOnClickListener(v -> {
            status.setText(identityText());
            append("monitor_status_refreshed", identityJson());
        });
        root.addView(refresh);

        Button copy = new Button(this);
        copy.setText("Copy report path");
        copy.setOnClickListener(v -> copyPaths());
        root.addView(copy);

        Button uploadConfig = new Button(this);
        uploadConfig.setText("Configure GitHub report upload");
        uploadConfig.setOnClickListener(v -> configureGithubToken());
        root.addView(uploadConfig);

        Button upload = new Button(this);
        upload.setText("Upload report to GitHub + copy URL");
        upload.setOnClickListener(v -> confirmUploadReport());
        root.addView(upload);

        Button paths = new Button(this);
        paths.setText("Copy report paths");
        paths.setOnClickListener(v -> copyPaths());
        root.addView(paths);

        Button crash = new Button(this);
        crash.setText("Check last Base App crash");
        crash.setOnClickListener(v -> checkLastCrashAndCopy());
        root.addView(crash);

        Button allTests = new Button(this);
        allTests.setText("TEST ALL FUNCTIONS + COPY REPORT");
        allTests.setOnClickListener(v -> requestFullTest());
        root.addView(allTests);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root);
        setContentView(scroll);
    }

    private File reportFile() { return new File(getFilesDir(), REPORT); }
    private File pidFile() { return new File(getFilesDir(), PID_FILE); }

    private String identityText() {
        return "MONITOR ALIVE\n"
            + "PID: " + Process.myPid() + "\n"
            + "UID: " + Process.myUid() + "\n"
            + "Process: " + Process.myProcessName() + "\n\n"
            + "Report:\n" + reportFile().getAbsolutePath() + "\n\n"
            + "Archive:\n" + new File(getFilesDir(),
                "yj64-reports/yj64-diagnostics.zip").getAbsolutePath();
    }

    private String identityJson() {
        return "{\"pid\":" + Process.myPid()
            + ",\"uid\":" + Process.myUid()
            + ",\"process_name\":\"" + escape(Process.myProcessName()) + "\"}";
    }

    private void copyPaths() {
        copyText(reportFile().getAbsolutePath() + "\n"
            + new File(getFilesDir(), "yj64-reports/yj64-diagnostics.zip").getAbsolutePath());
        Toast.makeText(this, "Report paths copied", Toast.LENGTH_SHORT).show();
    }

    private static final String GITHUB_KEY_ALIAS = "yj64_github_report_upload_key";
    private static final String GITHUB_TOKEN_FILE = "yj64-github-token.enc";
    private static final String GITHUB_OWNER = "concreteballs";
    private static final String GITHUB_REPO = "yj64-clean-bial2modFun";
    private static final String GITHUB_BRANCH = "main";

    private SecretKey githubEncryptionKey() throws Exception {
        KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore");
        keyStore.load(null);
        if (keyStore.containsAlias(GITHUB_KEY_ALIAS)) {
            return (SecretKey) keyStore.getKey(GITHUB_KEY_ALIAS, null);
        }
        KeyGenerator generator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(
            GITHUB_KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build());
        return generator.generateKey();
    }

    private File githubTokenFile() {
        return new File(getFilesDir(), GITHUB_TOKEN_FILE);
    }

    private void saveGithubToken(String token) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, githubEncryptionKey());
        byte[] encrypted = cipher.doFinal(token.trim().getBytes(StandardCharsets.UTF_8));
        byte[] iv = cipher.getIV();
        byte[] combined = new byte[iv.length + encrypted.length];
        System.arraycopy(iv, 0, combined, 0, iv.length);
        System.arraycopy(encrypted, 0, combined, iv.length, encrypted.length);
        try (FileOutputStream out = new FileOutputStream(githubTokenFile(), false)) {
            out.write(Base64.encode(combined, Base64.NO_WRAP));
            out.flush();
            out.getFD().sync();
        }
    }

    private String loadGithubToken() throws Exception {
        File file = githubTokenFile();
        if (!file.isFile()) return "";
        byte[] combined = Base64.decode(readFile(file), Base64.NO_WRAP);
        if (combined.length <= 12) throw new IOException("Stored GitHub token is invalid");
        byte[] iv = java.util.Arrays.copyOfRange(combined, 0, 12);
        byte[] encrypted = java.util.Arrays.copyOfRange(combined, 12, combined.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, githubEncryptionKey(), new GCMParameterSpec(128, iv));
        return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
    }

    private void configureGithubToken() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        input.setHint("Fine-grained GitHub token");
        new AlertDialog.Builder(this)
            .setTitle("GitHub report upload")
            .setMessage("Use a fine-grained token restricted to concreteballs/yj64-clean with Contents: Read and write. The token is encrypted with Android Keystore on this device; it is not embedded in the APK.")
            .setView(input)
            .setNegativeButton("CANCEL", (dialog, which) -> dialog.dismiss())
            .setPositiveButton("SAVE TOKEN", (dialog, which) -> {
                String token = input.getText().toString().trim();
                if (token.isEmpty()) {
                    Toast.makeText(this, "Token was empty", Toast.LENGTH_SHORT).show();
                    return;
                }
                try {
                    saveGithubToken(token);
                    append("github_report_token_saved", "{\"encrypted\":true}");
                    Toast.makeText(this, "GitHub token saved securely on this device", Toast.LENGTH_LONG).show();
                } catch (Exception e) {
                    append("github_report_token_save_failed",
                        "{\"error_type\":\"" + escape(e.getClass().getSimpleName()) + "\"}");
                    Toast.makeText(this, "Token save failed: " + e.getClass().getSimpleName(), Toast.LENGTH_LONG).show();
                }
            })
            .show();
    }

    private void confirmUploadReport() {
        new AlertDialog.Builder(this)
            .setTitle("Publish diagnostic report?")
            .setMessage("This uploads the complete JSONL report to the PUBLIC repository concreteballs/yj64-clean. It may contain prompts, model responses, and error details. Continue only if you are comfortable making those diagnostics public.")
            .setNegativeButton("CANCEL", (dialog, which) -> dialog.dismiss())
            .setPositiveButton("UPLOAD", (dialog, which) -> uploadReportToGitHub())
            .show();
    }

    private void uploadReportToGitHub() {
        final String token;
        try {
            token = loadGithubToken();
        } catch (Exception e) {
            Toast.makeText(this, "Could not decrypt GitHub token. Configure it again.", Toast.LENGTH_LONG).show();
            return;
        }
        if (token.isEmpty()) {
            Toast.makeText(this, "Configure a GitHub token first", Toast.LENGTH_LONG).show();
            configureGithubToken();
            return;
        }
        File file = reportFile();
        if (!file.isFile()) {
            Toast.makeText(this, "Report file does not exist yet", Toast.LENGTH_LONG).show();
            return;
        }
        final byte[] reportBytes;
        try (FileInputStream in = new FileInputStream(file);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
            reportBytes = out.toByteArray();
        } catch (IOException e) {
            Toast.makeText(this, "Report read failed: " + e.getClass().getSimpleName(), Toast.LENGTH_LONG).show();
            return;
        }
        final String timestamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date());
        // Keep one stable URL so the user can share it once and refresh the latest report.
        final String reportPath = "Report";
        status.setText(identityText() + "\n\nUploading report to GitHub...");
        new Thread(() -> {
            HttpURLConnection connection = null;
            try {
                URL url = new URL("https://api.github.com/repos/" + GITHUB_OWNER
                    + "/" + GITHUB_REPO + "/contents/" + reportPath);
                String existingSha = "";
                HttpURLConnection lookup = (HttpURLConnection) new URL(
                    "https://api.github.com/repos/" + GITHUB_OWNER + "/" + GITHUB_REPO
                    + "/contents/" + reportPath + "?ref=" + GITHUB_BRANCH).openConnection();
                lookup.setRequestMethod("GET");
                lookup.setConnectTimeout(15000);
                lookup.setReadTimeout(20000);
                lookup.setRequestProperty("Accept", "application/vnd.github+json");
                lookup.setRequestProperty("Authorization", "Bearer " + token);
                lookup.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
                int lookupCode = lookup.getResponseCode();
                if (lookupCode == HttpURLConnection.HTTP_OK) {
                    try (InputStream in = lookup.getInputStream();
                         ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                        byte[] buffer = new byte[4096];
                        int count;
                        while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
                        org.json.JSONObject existing = new org.json.JSONObject(
                            new String(out.toByteArray(), StandardCharsets.UTF_8));
                        existingSha = existing.optString("sha", "");
                    }
                } else if (lookupCode != HttpURLConnection.HTTP_NOT_FOUND) {
                    InputStream err = lookup.getErrorStream();
                    String detail = "";
                    if (err != null) {
                        try (InputStream in = err;
                             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                            byte[] buffer = new byte[2048];
                            int count;
                            while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
                            detail = new String(out.toByteArray(), StandardCharsets.UTF_8);
                        }
                    }
                    throw new IOException("GitHub lookup HTTP " + lookupCode + ": "
                        + detail.substring(0, Math.min(300, detail.length())));
                }
                lookup.disconnect();

                connection = (HttpURLConnection) url.openConnection();
                connection.setRequestMethod("PUT");
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(30000);
                connection.setDoOutput(true);
                connection.setRequestProperty("Accept", "application/vnd.github+json");
                connection.setRequestProperty("Authorization", "Bearer " + token);
                connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                org.json.JSONObject payload = new org.json.JSONObject();
                payload.put("message", "Update latest YJ-64 diagnostic report " + timestamp);
                payload.put("branch", GITHUB_BRANCH);
                payload.put("content", Base64.encodeToString(reportBytes, Base64.NO_WRAP));
                if (!existingSha.isEmpty()) payload.put("sha", existingSha);
                try (OutputStream out = connection.getOutputStream()) {
                    out.write(payload.toString().getBytes(StandardCharsets.UTF_8));
                    out.flush();
                }
                int code = connection.getResponseCode();
                InputStream responseStream = code >= 200 && code < 300
                    ? connection.getInputStream() : connection.getErrorStream();
                String responseText = "";
                if (responseStream != null) {
                    try (InputStream in = responseStream;
                         ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                        byte[] buffer = new byte[4096];
                        int count;
                        while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
                        responseText = new String(out.toByteArray(), StandardCharsets.UTF_8);
                    }
                }
                if (code < 200 || code >= 300) {
                    throw new IOException("GitHub HTTP " + code + ": " + responseText.substring(0, Math.min(500, responseText.length())));
                }
                org.json.JSONObject response = new org.json.JSONObject(responseText);
                org.json.JSONObject content = response.optJSONObject("content");
                String htmlUrl = content == null ? "" : content.optString("html_url", "");
                String returnedPath = content == null ? "" : content.optString("path", "");
                if (!"Report".equals(returnedPath) || htmlUrl.isEmpty()
                    || !htmlUrl.contains("/blob/" + GITHUB_BRANCH + "/Report")) {
                    throw new IOException("GitHub response did not confirm the expected Report path and branch");
                }
                final String publishedUrl = htmlUrl;
                append("github_report_upload_succeeded",
                    "{\"path\":\"" + escape(reportPath) + "\",\"url\":\"" + escape(publishedUrl) + "\",\"bytes\":" + reportBytes.length + "}");
                runOnUiThread(() -> {
                    copyText(publishedUrl);
                    status.setText(identityText() + "\n\nGitHub report URL copied:\n" + publishedUrl);
                    Toast.makeText(this, "Report uploaded; stable GitHub URL copied", Toast.LENGTH_LONG).show();
                });
            } catch (Exception e) {
                append("github_report_upload_failed",
                    "{\"path\":\"" + escape(reportPath) + "\",\"error_type\":\"" + escape(e.getClass().getSimpleName()) + "\",\"error\":\"" + escape(String.valueOf(e.getMessage())) + "\"}");
                runOnUiThread(() -> {
                    status.setText(identityText() + "\n\nGitHub upload failed: " + e.getClass().getSimpleName() + ": " + e.getMessage());
                    Toast.makeText(this, "GitHub upload failed: " + e.getClass().getSimpleName(), Toast.LENGTH_LONG).show();
                });
            } finally {
                if (connection != null) connection.disconnect();
            }
        }, "yj64-github-report-upload").start();
    }

    private void copyText(String text) {
        ClipboardManager clipboard =
            (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        clipboard.setPrimaryClip(ClipData.newPlainText("YJ-64", text));
    }

    private void pickConfigFile() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/json");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(intent, PICK_CONFIG_FILE);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_CONFIG_FILE || resultCode != RESULT_OK
                || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        try {
            File target = new File(getFilesDir(), "yj64-llm-config.json");
            try (InputStream in = getContentResolver().openInputStream(uri);
                 FileOutputStream out = new FileOutputStream(target, false)) {
                if (in == null) throw new IOException("Unable to open selected document");
                byte[] buffer = new byte[8192];
                int count;
                while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
                out.flush();
                out.getFD().sync();
            }
            append("llm_config_file_imported", "{}");
            status.setText(identityText() + "\n\nLLM config file imported.");
            Toast.makeText(this, "LLM config imported", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            append("llm_config_file_import_failed",
                "{\"error_type\":\"" + escape(e.getClass().getSimpleName()) + "\"}");
            Toast.makeText(this, "Import failed: " + e, Toast.LENGTH_LONG).show();
        }
    }

    private void checkLastCrashAndCopy() {
        append("last_crash_check_started", "{}");
        String result = lastExitReport();
        append("last_crash_check_completed",
            "{\"report\":\"" + escape(result) + "\"}");
        copyText(result + "\n\n--- YJ-64 REPORT ---\n" + readReport());
        status.setText(result);
        Toast.makeText(this, "Crash report copied", Toast.LENGTH_SHORT).show();
    }

    private String lastExitReport() {
        if (android.os.Build.VERSION.SDK_INT < 30) {
            return "ApplicationExitInfo unavailable below Android 11.";
        }
        ActivityManager am = (ActivityManager) getSystemService(ACTIVITY_SERVICE);
        java.util.List<ApplicationExitInfo> exits =
            am.getHistoricalProcessExitReasons(getPackageName(), 0, 10);
        if (exits == null || exits.isEmpty()) return "No historical Base App exits reported.";
        StringBuilder out = new StringBuilder("YJ-64 LAST BASE APP EXIT(S)\n");
        for (ApplicationExitInfo info : exits) {
            out.append("time_ms=").append(info.getTimestamp())
                .append(", reason=").append(reasonName(info.getReason()))
                .append(", status=").append(info.getStatus())
                .append(", pid=").append(info.getPid()).append("\n");
            if (info.getDescription() != null) {
                out.append("description=").append(info.getDescription()).append("\n");
            }
        }
        return out.toString().trim();
    }

    private String reasonName(int reason) {
        switch (reason) {
            case ApplicationExitInfo.REASON_CRASH: return "CRASH";
            case ApplicationExitInfo.REASON_ANR: return "ANR";
            case ApplicationExitInfo.REASON_LOW_MEMORY: return "LOW_MEMORY";
            case ApplicationExitInfo.REASON_USER_REQUESTED: return "USER_REQUESTED";
            case ApplicationExitInfo.REASON_SIGNALED: return "SIGNALED";
            case ApplicationExitInfo.REASON_INITIALIZATION_FAILURE: return "INITIALIZATION_FAILURE";
            case ApplicationExitInfo.REASON_PERMISSION_CHANGE: return "PERMISSION_CHANGE";
            case ApplicationExitInfo.REASON_EXCESSIVE_RESOURCE_USAGE: return "EXCESSIVE_RESOURCE_USAGE";
            default: return "REASON_" + reason;
        }
    }

    private void requestFullTest() {
        final String testId = UUID.randomUUID().toString().replace("-", "");
        File command = new File(getFilesDir(), "yj64-test-command.json");
        File result = new File(getFilesDir(), "yj64-test-result.json");
        try {
            if (result.exists()) result.delete();
            String json = "{\"action\":\"full_test\",\"test_id\":\"" + testId + "\"}";
            try (FileOutputStream out = new FileOutputStream(command, false)) {
                out.write(json.getBytes(StandardCharsets.UTF_8));
                out.flush();
                out.getFD().sync();
            }
            append("full_test_requested", "{\"test_id\":\"" + testId + "\"}");
            status.setText(identityText() + "\n\nFull function test requested...");
            new Thread(() -> waitForFullTest(testId)).start();
        } catch (IOException e) {
            Toast.makeText(this, "Full test request failed: " + e, Toast.LENGTH_LONG).show();
        }
    }

    private void waitForFullTest(String testId) {
        long deadline = System.currentTimeMillis() + 120000L;
        while (System.currentTimeMillis() < deadline) {
            File result = new File(getFilesDir(), "yj64-test-result.json");
            if (result.isFile()) {
                try {
                    String text = readFile(result);
                    if (text.contains("\"test_id\":\"" + testId + "\"")) {
                        String report = readReport();
                        append("full_test_result_collected",
                            "{\"test_id\":\"" + testId + "\"}");
                        runOnUiThread(() -> {
                            copyPaths();
                            status.setText(identityText() + "\n\nFull test completed. Report paths copied.");
                            Toast.makeText(this, "Full test completed; report paths copied", Toast.LENGTH_SHORT).show();
                        });
                        return;
                    }
                } catch (Exception ignored) {}
            }
            try { Thread.sleep(500); }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
        }
        runOnUiThread(() -> Toast.makeText(
            this, "Full test timed out; copy report manually.", Toast.LENGTH_LONG).show());
    }

    private String readReport() {
        File file = reportFile();
        return file.exists() ? readFile(file) : "Report file does not exist.";
    }

    private String readFile(File file) {
        StringBuilder text = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) text.append(line).append('\n');
        } catch (IOException e) {
            return "Read failed: " + e;
        }
        return text.toString();
    }


    private int readMainPid() {
        try (BufferedReader reader = new BufferedReader(new FileReader(pidFile()))) {
            return Integer.parseInt(reader.readLine().trim());
        } catch (Exception e) { return -1; }
    }

    private void append(String event, String data) {
        File file = reportFile();
        File parent = file.getParentFile();
        if (parent != null) parent.mkdirs();
        String line = "{\"schema\":\"yj64.diagnostic.v1\","
            + "\"agent\":\"yj64-internal-monitor\","
            + "\"event\":\"" + escape(event) + "\","
            + "\"timestamp_ms\":" + System.currentTimeMillis() + ","
            + "\"message_id\":\"MON-" + UUID.randomUUID().toString().replace("-", "") + "\","
            + "\"data\":" + data + "}\n";
        try (FileOutputStream out = new FileOutputStream(file, true)) {
            out.write(line.getBytes(StandardCharsets.UTF_8));
            out.flush();
            out.getFD().sync();
        } catch (IOException ignored) {}
    }

    private String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
