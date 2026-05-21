using System.Diagnostics;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace InstallLauncher;

internal sealed record InstallOptions(
    string Host,
    string HostPath,
    string GameDir,
    string SkillsDir,
    string PythonPath
);

internal static class Deployer
{
    public static string ExtractPayloadZip(Stream payloadStream, string tempRoot)
    {
        var extractDir = Path.Combine(tempRoot, "STS2_Skills_payload");
        if (Directory.Exists(extractDir))
            Directory.Delete(extractDir, true);
        Directory.CreateDirectory(extractDir);
        using var zip = new ZipArchive(payloadStream, ZipArchiveMode.Read);
        zip.ExtractToDirectory(extractDir, overwriteFiles: true);
        var inner = Path.Combine(extractDir, "STS2_Skills");
        return Directory.Exists(inner) ? inner : extractDir;
    }

    public static void DeployAll(InstallOptions opt, string payloadRoot, Action<string>? log = null)
    {
        void L(string msg) => log?.Invoke(msg);

        L($"{I18n.StepExtract} → {opt.SkillsDir}");
        CopyTree(payloadRoot, opt.SkillsDir);

        L($"{I18n.StepMod} → {Path.Combine(opt.GameDir, "mods")}");
        InstallMod(payloadRoot, opt.GameDir, L);

        L($"{I18n.StepHost}: {opt.Host}");
        RunHostSetup(opt, L);

        L(I18n.StepPip);
        TryPipInstall(opt, L);
    }

    private static void CopyTree(string src, string dst)
    {
        if (Directory.Exists(dst))
            Directory.Delete(dst, true);
        CopyDirectoryRecursive(src, dst);
    }

    private static void CopyDirectoryRecursive(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (var dir in Directory.GetDirectories(src))
        {
            var name = Path.GetFileName(dir);
            if (name is ".git" or "__pycache__" or "dist" or "build" or ".venv" or "venv")
                continue;
            CopyDirectoryRecursive(dir, Path.Combine(dst, name));
        }
        foreach (var file in Directory.GetFiles(src))
        {
            var name = Path.GetFileName(file);
            if (name is "install.exe" or "sts2skill.exe" or "payload.zip")
                continue;
            File.Copy(file, Path.Combine(dst, name), overwrite: true);
        }
    }

    private static void InstallMod(string payloadRoot, string gameDir, Action<string> log)
    {
        var modsDir = Path.Combine(gameDir, "mods");
        Directory.CreateDirectory(modsDir);
        var bundled = Path.Combine(payloadRoot, "payload", "mods");
        if (Directory.Exists(bundled))
        {
            foreach (var name in new[] { "STS2_MCP.dll", "STS2_MCP.json" })
            {
                var src = Path.Combine(bundled, name);
                if (File.Exists(src))
                    File.Copy(src, Path.Combine(modsDir, name), overwrite: true);
            }
            log(I18n.T("  模组文件已写入。", "  Mod files written."));
            return;
        }
        log(I18n.T(
            "  安装包内无模组，请稍后运行 sts2 install-mod",
            "  No bundled mod; run sts2 install-mod later"));
    }

    private static string? SkillDirForHost(InstallOptions opt) => opt.Host switch
    {
        "openclaw" => Path.Combine(opt.HostPath, "workspace", "skills"),
        "astrbot" => Path.Combine(opt.HostPath, "plugins", "astrbot_plugin_sts2_agent", "skills"),
        "hermes" => Path.Combine(opt.HostPath, "skills"),
        _ => null,
    };

    private static void RunHostSetup(InstallOptions opt, Action<string> log)
    {
        var script = Path.Combine(opt.SkillsDir, "scripts", "sts2_host_setup_cli.py");
        if (!File.Exists(script))
        {
            log(I18n.T(
                $"  缺少 {script}，无法配置宿主。",
                $"  Missing {script}; host setup skipped."));
            return;
        }

        if (string.IsNullOrWhiteSpace(opt.PythonPath) || !File.Exists(opt.PythonPath))
        {
            log(I18n.T(
                "  跳过宿主配置（未找到 Python）",
                "  Skip host setup (Python not found)"));
            return;
        }

        var args = new StringBuilder();
        args.Append('"').Append(script).Append('"');
        args.Append(" --host ").Append(opt.Host);
        args.Append(" --repo-root \"").Append(opt.SkillsDir).Append('"');
        args.Append(" --game-dir \"").Append(opt.GameDir).Append('"');
        args.Append(" --python \"").Append(opt.PythonPath).Append('"');
        args.Append(" --json");

        if (opt.Host == "openclaw")
            args.Append(" --openclaw-home \"").Append(opt.HostPath).Append('"');
        else if (opt.Host == "astrbot")
            args.Append(" --astrbot-data \"").Append(opt.HostPath).Append('"');

        var skillDir = SkillDirForHost(opt);
        if (!string.IsNullOrEmpty(skillDir))
            args.Append(" --skill-dir \"").Append(skillDir).Append('"');

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = opt.PythonPath,
                Arguments = args.ToString(),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
                WorkingDirectory = opt.SkillsDir,
            };
            using var proc = Process.Start(psi);
            if (proc is null)
            {
                log(I18n.T("  宿主配置进程启动失败", "  Failed to start host setup process"));
                return;
            }
            var stdout = proc.StandardOutput.ReadToEnd();
            var stderr = proc.StandardError.ReadToEnd();
            proc.WaitForExit();

            if (!string.IsNullOrWhiteSpace(stdout))
            {
                try
                {
                    var node = JsonNode.Parse(stdout) as JsonObject;
                    if (node is not null)
                    {
                        if (node["messages"] is JsonArray msgs)
                        {
                            foreach (var item in msgs)
                            {
                                var line = item?.GetValue<string>();
                                if (!string.IsNullOrWhiteSpace(line))
                                    log("  " + line);
                            }
                        }
                        if (node["warnings"] is JsonArray warns)
                        {
                            foreach (var item in warns)
                            {
                                var line = item?.GetValue<string>();
                                if (!string.IsNullOrWhiteSpace(line))
                                    log(I18n.T($"  警告: {line}", $"  Warning: {line}"));
                            }
                        }
                        var ok = node["ok"]?.GetValue<bool>() ?? false;
                        if (!ok || proc.ExitCode != 0)
                            log(I18n.T(
                                "  宿主配置未完全成功（见日志）",
                                "  Host setup incomplete (see log)"));
                        return;
                    }
                }
                catch
                {
                    foreach (var line in stdout.Split('\n', StringSplitOptions.RemoveEmptyEntries))
                        log("  " + line.Trim());
                }
            }

            if (!string.IsNullOrWhiteSpace(stderr))
                log("  " + stderr.Trim());

            if (proc.ExitCode != 0)
                log(I18n.T(
                    $"  宿主配置退出码 {proc.ExitCode}",
                    $"  Host setup exit code {proc.ExitCode}"));
        }
        catch (Exception ex)
        {
            log(I18n.T(
                $"  宿主配置异常: {ex.Message}",
                $"  Host setup error: {ex.Message}"));
        }
    }

    private static void TryPipInstall(InstallOptions opt, Action<string> log)
    {
        if (string.IsNullOrWhiteSpace(opt.PythonPath) || !File.Exists(opt.PythonPath))
        {
            log(I18n.T(
                "  跳过 pip（未配置 Python）",
                "  Skip pip (Python not set)"));
            return;
        }
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = opt.PythonPath,
                Arguments = $"-m pip install -e \"{opt.SkillsDir}[mcp]\"",
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using var p = Process.Start(psi);
            p?.WaitForExit();
            log(p?.ExitCode == 0
                ? I18n.T("  pip 完成", "  pip OK")
                : I18n.T("  pip 失败，请手动安装", "  pip failed, install manually"));
        }
        catch (Exception ex)
        {
            log($"  pip: {ex.Message}");
        }
    }
}
