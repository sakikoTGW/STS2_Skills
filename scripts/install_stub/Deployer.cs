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
    int Character,
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
        switch (opt.Host)
        {
            case "astrbot":
                SetupAstrBot(opt, L);
                break;
            case "hermes":
                SetupHermes(opt, L);
                break;
            case "openclaw":
                SetupOpenClaw(opt, L);
                break;
            default:
                SetupStandalone(opt, L);
                break;
        }

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
            "  安装包内无模组，请稍后运行 install_sts2_mcp_mod.py",
            "  No bundled mod; run install_sts2_mcp_mod.py later"));
    }

    private static void SetupStandalone(InstallOptions opt, Action<string> log)
    {
        var sts2Home = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".config", "sts2");
        WriteSts2Config(sts2Home, opt.Character);
        log($"  {sts2Home}\\config.yaml");
    }

    private static void SetupHermes(InstallOptions opt, Action<string> log)
    {
        var hermesHome = opt.HostPath;
        var sts2Home = Path.Combine(hermesHome, "sts2");
        WriteSts2Config(sts2Home, opt.Character);
        MergeHermesConfig(hermesHome, opt.Character);
        CopySkill(
            Path.Combine(opt.SkillsDir, "skills", "slay-the-spire-2"),
            Path.Combine(hermesHome, "skills", "slay-the-spire-2"),
            log);
        log($"  Hermes: {hermesHome}");
    }

    private static void SetupOpenClaw(InstallOptions opt, Action<string> log)
    {
        var ocHome = opt.HostPath;
        var sts2Home = Path.Combine(ocHome, "sts2");
        WriteSts2Config(sts2Home, opt.Character);
        var block = BuildMcpBlock(opt.SkillsDir, opt.PythonPath, sts2Home, opt.Character);
        var mcpPath = Path.Combine(ocHome, "mcp.sts2.json");
        File.WriteAllText(mcpPath, block.ToJsonString(new JsonSerializerOptions { WriteIndented = true }), Encoding.UTF8);
        log($"  {mcpPath}");
        CopySkill(
            Path.Combine(opt.SkillsDir, "skills", "slay-the-spire-2"),
            Path.Combine(ocHome, "workspace", "skills", "slay-the-spire-2"),
            log);
    }

    private static void SetupAstrBot(InstallOptions opt, Action<string> log)
    {
        var data = opt.HostPath;
        var sts2Home = Path.Combine(data, "sts2");
        WriteSts2Config(sts2Home, opt.Character);

        var pluginSrc = Path.Combine(opt.SkillsDir, "plugins", "sts2", "integrations", "astrbot", "plugin");
        var pluginDst = Path.Combine(data, "plugins", "astrbot_plugin_sts2_agent");
        if (Directory.Exists(pluginSrc))
        {
            CopyTree(pluginSrc, pluginDst);
            log($"  {pluginDst}");
        }

        var skillSrc = Path.Combine(opt.SkillsDir, "skills", "slay-the-spire-2");
        var skillDst = Path.Combine(pluginDst, "skills", "slay-the-spire-2");
        CopySkill(skillSrc, skillDst, log);

        var mcpBlock = BuildMcpBlock(opt.SkillsDir, opt.PythonPath, sts2Home, opt.Character);
        mcpBlock["env"]!["STS2_CONFIG_PATH"] = Path.Combine(sts2Home, "config.yaml");
        mcpBlock["env"]!["ASTRBOT_DATA"] = data;
        MergeAstrBotMcp(data, mcpBlock, log);

        var cfgDir = Path.Combine(data, "config");
        Directory.CreateDirectory(cfgDir);
        var plugPath = Path.Combine(cfgDir, "astrbot_plugin_sts2_agent_config.json");
        var plug = ReadJsonObject(plugPath);
        plug["skills_root"] = opt.SkillsDir;
        plug["base_url"] = "http://127.0.0.1:15526";
        plug["character"] = opt.Character;
        plug["game_dir"] = opt.GameDir;
        plug["mcp_python"] = opt.PythonPath;
        if (!plug.ContainsKey("interval")) plug["interval"] = 0.7;
        if (!plug.ContainsKey("llm_min_interval")) plug["llm_min_interval"] = 4.0;
        if (!plug.ContainsKey("llm_post_think_delay")) plug["llm_post_think_delay"] = 1.2;
        if (!plug.ContainsKey("llm_provider_id")) plug["llm_provider_id"] = "";
        File.WriteAllText(plugPath, plug.ToJsonString(new JsonSerializerOptions { WriteIndented = true }), Encoding.UTF8);
        log($"  {plugPath}");
    }

    private static void CopySkill(string src, string dst, Action<string> log)
    {
        if (!Directory.Exists(src))
        {
            log(I18n.T($"  跳过 Skill: {src}", $"  Skip skill: {src}"));
            return;
        }
        if (Directory.Exists(dst))
            Directory.Delete(dst, true);
        CopyDirectoryRecursive(src, dst);
        log($"  {dst}");
    }

    private static JsonObject BuildMcpBlock(string skillsRoot, string python, string sts2Home, int character)
    {
        var bridge = Path.Combine(skillsRoot, "scripts", "sts2_mcp_bridge.py");
        return new JsonObject
        {
            ["command"] = python,
            ["args"] = new JsonArray { bridge },
            ["env"] = new JsonObject
            {
                ["STS2_MCP_BASE_URL"] = "http://127.0.0.1:15526",
                ["STS2_HOME"] = sts2Home,
                ["STS2_CHARACTER"] = character.ToString(),
            },
        };
    }

    private static void MergeAstrBotMcp(string dataDir, JsonObject block, Action<string> log)
    {
        var path = Path.Combine(dataDir, "mcp_server.json");
        var root = ReadJsonObject(path);
        if (root["mcpServers"] is not JsonObject servers)
        {
            servers = new JsonObject();
            root["mcpServers"] = servers;
        }
        servers["sts2"] = block;
        File.WriteAllText(path, root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }), Encoding.UTF8);
        log($"  MCP: {path}");
    }

    private static void MergeHermesConfig(string hermesHome, int character)
    {
        var path = Path.Combine(hermesHome, "config.yaml");
        var block = new StringBuilder();
        block.AppendLine("sts2:");
        block.AppendLine("  base_url: http://127.0.0.1:15526");
        block.AppendLine($"  character: {character}");
        block.AppendLine("  pause_on_ask: false");
        block.AppendLine("  ask_user_on: []");
        if (File.Exists(path))
        {
            var text = File.ReadAllText(path, Encoding.UTF8);
            if (!text.Contains("sts2:", StringComparison.Ordinal))
                File.AppendAllText(path, "\n" + block, Encoding.UTF8);
        }
        else
        {
            Directory.CreateDirectory(hermesHome);
            File.WriteAllText(path, block.ToString(), Encoding.UTF8);
        }
    }

    private static JsonObject ReadJsonObject(string path)
    {
        if (!File.Exists(path))
            return new JsonObject();
        try
        {
            return JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8)) as JsonObject ?? new JsonObject();
        }
        catch
        {
            return new JsonObject();
        }
    }

    private static void WriteSts2Config(string sts2Home, int character)
    {
        Directory.CreateDirectory(sts2Home);
        var yaml = new StringBuilder();
        yaml.AppendLine("sts2:");
        yaml.AppendLine("  base_url: http://127.0.0.1:15526");
        yaml.AppendLine("  timeout: 15");
        yaml.AppendLine($"  character: {character}");
        yaml.AppendLine("  commentary: verbose");
        yaml.AppendLine("  autoplay: false");
        yaml.AppendLine("  pause_on_ask: false");
        yaml.AppendLine("  ask_user_on: []");
        yaml.AppendLine("  autopilot_until_victory: true");
        yaml.AppendLine("  study_marathon: true");
        yaml.AppendLine("  loop_runs: true");
        File.WriteAllText(Path.Combine(sts2Home, "config.yaml"), yaml.ToString(), Encoding.UTF8);
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
            var psi = new System.Diagnostics.ProcessStartInfo
            {
                FileName = opt.PythonPath,
                Arguments = $"-m pip install -e \"{opt.SkillsDir}[mcp]\"",
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using var p = System.Diagnostics.Process.Start(psi);
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
