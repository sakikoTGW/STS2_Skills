using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace InstallLauncher;

internal static class PathHelper
{
    public static string DefaultHostPath(string host) => host switch
    {
        "astrbot" => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".astrbot", "data"),
        "openclaw" => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".openclaw"),
        "hermes" => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".hermes"),
        _ => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "STS2_Skills"),
    };

    public static IEnumerable<string> HostPathCandidates(string host)
    {
        yield return DefaultHostPath(host);
        if (host == "astrbot")
        {
            yield return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                "AstrBot", "data");
        }
    }

    public static string? DetectHostPath(string host)
    {
        foreach (var cand in HostPathCandidates(host))
        {
            if (Directory.Exists(cand))
                return cand;
        }
        return DefaultHostPath(host);
    }

    public static string DefaultSkillsPath(string host, string hostPath)
    {
        if (host == "standalone")
            return hostPath;
        var parent = Path.GetDirectoryName(hostPath.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
        return Path.Combine(parent ?? hostPath, "STS2_Skills");
    }

    public static string? FindPythonForAstrBot()
    {
        var user = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        foreach (var c in new[]
        {
            Path.Combine(user, "AstrBot", "backend", "python", "python.exe"),
            Path.Combine(user, "Programs", "AstrBot", "backend", "python", "python.exe"),
        })
        {
            if (File.Exists(c))
                return c;
        }
        return FindOnPath("python") ?? FindOnPath("py");
    }

    public static string? FindOnPath(string name)
    {
        var pathEnv = Environment.GetEnvironmentVariable("PATH");
        if (string.IsNullOrEmpty(pathEnv))
            return null;
        var exts = (Environment.GetEnvironmentVariable("PATHEXT") ?? ".EXE").Split(';');
        foreach (var dir in pathEnv.Split(Path.PathSeparator))
        {
            foreach (var ext in exts)
            {
                var full = Path.Combine(dir.Trim(), name + ext);
                if (File.Exists(full))
                    return full;
            }
        }
        return null;
    }

    public static string HostPathHint(string host) => host switch
    {
        "astrbot" => I18n.HostPathHintAstrBot,
        "openclaw" => I18n.HostPathHintOpenClaw,
        "hermes" => I18n.HostPathHintHermes,
        _ => I18n.HostPathHintStandalone,
    };

    public static bool LooksLikeGameDir(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Directory.Exists(path))
            return false;
        return File.Exists(Path.Combine(path, "SlayTheSpire2.exe"));
    }

    public static string? FindGameDir()
    {
        var env = Environment.GetEnvironmentVariable("STS2_GAME_DIR");
        if (!string.IsNullOrWhiteSpace(env) && LooksLikeGameDir(env))
            return Path.GetFullPath(env);

        foreach (var hint in GameDirHintFiles())
        {
            if (!File.Exists(hint))
                continue;
            try
            {
                var raw = File.ReadAllText(hint).Trim();
                if (LooksLikeGameDir(raw))
                    return Path.GetFullPath(raw);
            }
            catch { /* ignore */ }
        }

        foreach (var root in SteamInstallCandidates())
        {
            if (LooksLikeGameDir(root))
                return Path.GetFullPath(root);
        }

        return null;
    }

    private static IEnumerable<string> GameDirHintFiles()
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        foreach (var baseDir in new[]
        {
            Path.Combine(home, ".config", "sts2"),
            Path.Combine(home, ".hermes"),
            Path.Combine(home, ".hermes", "sts2"),
            Path.Combine(home, ".openclaw"),
            Path.Combine(home, ".openclaw", "sts2"),
            Path.Combine(home, ".astrbot", "data"),
            Path.Combine(home, ".astrbot", "data", "sts2"),
            Path.Combine(home, "AstrBot", "data"),
        })
        {
            yield return Path.Combine(baseDir, "game_dir.txt");
        }
    }

    private static IEnumerable<string> SteamInstallCandidates()
    {
        var rel = Path.Combine("steamapps", "common", "Slay the Spire 2");
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var libs = new List<string>();

        void Add(string? p)
        {
            if (string.IsNullOrWhiteSpace(p))
                return;
            var full = Path.GetFullPath(p);
            if (seen.Add(full))
                libs.Add(full);
        }

        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
            var steamPath = key?.GetValue("SteamPath") as string;
            if (!string.IsNullOrWhiteSpace(steamPath))
            {
                Add(steamPath);
                Add(Path.Combine(steamPath, rel));
                foreach (var lib in ParseSteamLibraryFolders(Path.Combine(steamPath, "steamapps", "libraryfolders.vdf")))
                {
                    Add(lib);
                    Add(Path.Combine(lib, rel));
                }
            }
        }
        catch { /* ignore */ }

        foreach (var drive in DriveInfo.GetDrives())
        {
            if (drive.DriveType != DriveType.Fixed || !drive.IsReady)
                continue;
            foreach (var sub in new[] { "Steam", "SteamLibrary" })
            {
                var steamRoot = Path.Combine(drive.Name, sub);
                Add(steamRoot);
                Add(Path.Combine(steamRoot, rel));
                var vdf = Path.Combine(steamRoot, "steamapps", "libraryfolders.vdf");
                foreach (var lib in ParseSteamLibraryFolders(vdf))
                {
                    Add(lib);
                    Add(Path.Combine(lib, rel));
                }
            }
        }

        return libs;
    }

    private static IEnumerable<string> ParseSteamLibraryFolders(string vdfPath)
    {
        if (!File.Exists(vdfPath))
            yield break;
        string raw;
        try
        {
            raw = File.ReadAllText(vdfPath);
        }
        catch
        {
            yield break;
        }
        foreach (Match m in Regex.Matches(raw, "\"path\"\\s+\"([^\"]+)\""))
        {
            var p = m.Groups[1].Value.Replace("\\\\", "\\");
            if (Directory.Exists(p))
                yield return p;
        }
    }

    /// <summary>Fill empty path fields; optional force refresh host-derived paths on host change.</summary>
    public static void ApplyAutoDetect(
        string host,
        TextBox hostPath,
        TextBox gamePath,
        TextBox skillsPath,
        TextBox python,
        bool refreshHostDerived)
    {
        if (refreshHostDerived || string.IsNullOrWhiteSpace(hostPath.Text))
            hostPath.Text = DetectHostPath(host) ?? DefaultHostPath(host);

        var hp = hostPath.Text.Trim();
        if (refreshHostDerived || string.IsNullOrWhiteSpace(skillsPath.Text))
            skillsPath.Text = DefaultSkillsPath(host, hp);

        if (string.IsNullOrWhiteSpace(gamePath.Text))
        {
            var game = FindGameDir();
            if (!string.IsNullOrEmpty(game))
                gamePath.Text = game;
        }

        if (string.IsNullOrWhiteSpace(python.Text))
        {
            var py = host == "astrbot" ? FindPythonForAstrBot() : FindOnPath("python");
            if (!string.IsNullOrEmpty(py))
                python.Text = py;
        }
    }
}
