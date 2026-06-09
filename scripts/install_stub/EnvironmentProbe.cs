using System.Diagnostics;

namespace InstallLauncher;

internal sealed record InstallReadiness(
    bool SkillsReady,
    bool ModReady,
    bool HostReady,
    bool PipReady,
    string SkillsDetail,
    string ModDetail,
    string HostDetail,
    string PipDetail)
{
    public bool AllReady => SkillsReady && ModReady && HostReady && PipReady;

    public bool NeedsDeploy(bool force) => force || !SkillsReady || !ModReady || !HostReady || !PipReady;
}

internal static class EnvironmentProbe
{
    public static InstallReadiness Probe(InstallOptions opt) =>
        new(
            SkillsReady: CheckSkills(opt.SkillsDir, out var sd),
            ModReady: CheckMod(opt.GameDir, out var md),
            HostReady: CheckHost(opt, out var hd),
            PipReady: CheckPip(opt, out var pd),
            sd,
            md,
            hd,
            pd);

    private static string Norm(string path) =>
        Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

    private static bool PathMatches(string haystack, string needle)
    {
        if (string.IsNullOrWhiteSpace(haystack) || string.IsNullOrWhiteSpace(needle))
            return false;
        return haystack.Contains(Norm(needle), StringComparison.OrdinalIgnoreCase);
    }

    private static bool CheckSkills(string skillsDir, out string detail)
    {
        detail = "";
        if (string.IsNullOrWhiteSpace(skillsDir) || !Directory.Exists(skillsDir))
        {
            detail = I18n.ProbeSkillsMissing;
            return false;
        }
        var root = Norm(skillsDir);
        var markers = new[]
        {
            Path.Combine(root, "pyproject.toml"),
            Path.Combine(root, "plugins", "sts2", "cli.py"),
            Path.Combine(root, "scripts", "sts2_host_setup_cli.py"),
            Path.Combine(root, "scripts", "sts2_mcp_bridge.py"),
        };
        foreach (var p in markers)
        {
            if (!File.Exists(p))
            {
                detail = I18n.ProbeSkillsIncomplete;
                return false;
            }
        }
        detail = I18n.ProbeSkillsOk;
        return true;
    }

    private static bool CheckMod(string gameDir, out string detail)
    {
        detail = "";
        if (!PathHelper.LooksLikeGameDir(gameDir))
        {
            detail = I18n.ProbeModNoGame;
            return false;
        }
        var mods = Path.Combine(gameDir, "mods");
        var dll = Path.Combine(mods, "STS2_MCP.dll");
        if (File.Exists(dll))
        {
            detail = I18n.ProbeModOk;
            return true;
        }
        if (Directory.Exists(mods) && Directory.EnumerateFiles(mods, "*MCP*.dll").Any())
        {
            detail = I18n.ProbeModOk;
            return true;
        }
        detail = I18n.ProbeModMissing;
        return false;
    }

    private static string Sts2Home(string host, string hostPath) => host switch
    {
        "openclaw" or "astrbot" or "hermes" => Path.Combine(hostPath, "sts2"),
        _ => hostPath,
    };

    private static bool GameDirHintMatches(string sts2Home, string gameDir)
    {
        var hint = Path.Combine(sts2Home, "game_dir.txt");
        if (!File.Exists(hint))
            return true;
        try
        {
            var saved = File.ReadAllText(hint).Trim();
            return string.Equals(Norm(saved), Norm(gameDir), StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return true;
        }
    }

    private static bool CheckHost(InstallOptions opt, out string detail)
    {
        detail = "";
        if (!Directory.Exists(opt.HostPath))
        {
            detail = I18n.ProbeHostMissing;
            return false;
        }

        var skills = Norm(opt.SkillsDir);
        var bridge = Path.Combine(skills, "scripts", "sts2_mcp_bridge.py").Replace('\\', '/');
        var sts2Home = Sts2Home(opt.Host, opt.HostPath);
        if (!GameDirHintMatches(sts2Home, opt.GameDir))
        {
            detail = I18n.ProbeHostGameMismatch;
            return false;
        }

        var ok = opt.Host switch
        {
            "astrbot" => CheckAstrBotMcp(opt.HostPath, skills, bridge),
            "openclaw" => CheckOpenClawMcp(opt.HostPath, skills, bridge),
            "hermes" => CheckHermesMcp(opt.HostPath, skills, bridge),
            _ => CheckStandaloneMcp(opt.HostPath, skills, bridge),
        };
        detail = ok ? I18n.ProbeHostOk : I18n.ProbeHostMismatch;
        return ok;
    }

    private static bool CheckAstrBotMcp(string dataDir, string skillsDir, string bridgePath)
    {
        var mcp = Path.Combine(dataDir, "mcp_server.json");
        if (!File.Exists(mcp))
            return false;
        var text = File.ReadAllText(mcp);
        if (!text.Contains("\"sts2\"", StringComparison.OrdinalIgnoreCase))
            return false;
        if (!PathMatches(text, bridgePath) && !PathMatches(text, skillsDir))
            return false;
        var plug = Path.Combine(dataDir, "plugins", "astrbot_plugin_sts2_agent");
        return Directory.Exists(plug);
    }

    private static bool CheckOpenClawMcp(string ocHome, string skillsDir, string bridgePath)
    {
        foreach (var name in new[] { "openclaw.json", "config.json" })
        {
            var p = Path.Combine(ocHome, name);
            if (!File.Exists(p))
                continue;
            var text = File.ReadAllText(p);
            if (text.Contains("sts2", StringComparison.OrdinalIgnoreCase)
                && (PathMatches(text, bridgePath) || PathMatches(text, skillsDir)))
                return true;
        }
        var snippet = Path.Combine(ocHome, "mcp.sts2.json");
        return File.Exists(snippet) && PathMatches(File.ReadAllText(snippet), bridgePath);
    }

    private static bool CheckHermesMcp(string hermesHome, string skillsDir, string bridgePath)
    {
        var cfg = Path.Combine(hermesHome, "config.yaml");
        if (!File.Exists(cfg))
            return false;
        var text = File.ReadAllText(cfg);
        return text.Contains("sts2", StringComparison.OrdinalIgnoreCase)
            && (PathMatches(text, bridgePath) || PathMatches(text, skillsDir));
    }

    private static bool CheckStandaloneMcp(string hostPath, string skillsDir, string bridgePath)
    {
        var snippet = Path.Combine(hostPath, "mcp.sts2.json");
        if (File.Exists(snippet) && PathMatches(File.ReadAllText(snippet), bridgePath))
            return true;
        var alt = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".config", "sts2", "mcp.sts2.json");
        return File.Exists(alt) && PathMatches(File.ReadAllText(alt), bridgePath);
    }

    private static bool CheckPip(InstallOptions opt, out string detail)
    {
        detail = "";
        if (string.IsNullOrWhiteSpace(opt.PythonPath) || !File.Exists(opt.PythonPath))
        {
            detail = I18n.ProbePipSkip;
            return false;
        }
        if (!CheckSkills(opt.SkillsDir, out _))
        {
            detail = I18n.ProbePipNeedSkills;
            return false;
        }
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = opt.PythonPath,
                Arguments = "-c \"import plugins.sts2; print('ok')\"",
                WorkingDirectory = opt.SkillsDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using var proc = Process.Start(psi);
            if (proc is null)
            {
                detail = I18n.ProbePipMissing;
                return false;
            }
            proc.WaitForExit(8000);
            if (proc.ExitCode == 0)
            {
                detail = I18n.ProbePipOk;
                return true;
            }
        }
        catch
        {
            /* fall through */
        }
        detail = I18n.ProbePipMissing;
        return false;
    }
}
