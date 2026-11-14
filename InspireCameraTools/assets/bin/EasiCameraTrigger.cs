// EasiCameraTrigger — 亿方展台管家外部触发助手
//
// 用途：不依赖键盘快捷键，直接驱动希沃视频展台（EasiCamera）拍照：
//   1) capture / probe（默认）：通过 UI Automation 找到界面上的「拍照」按钮并 Invoke，
//      等价于用户点击拍照按钮（EasiCamera 内部同样执行 ECCommands.CaptureImage）。
//      不占用/不写 HID，不需要 EasiCamera 前台焦点，不受希沃进程独占 HID 影响。
//   2) remoting（诊断/备用）：通过 EasiCamera 的 .NET Remoting IPC 通道
//      Ipc://e3950283-80cf-4a97-a569-e6110b6e9b82/RemotingNotifyCamera 调用
//      Notify(pid, vid, "Key5")，即 Guardian 转发机身按键的同一入口。
//      注意：服务器对象 RemotingNotifyCamera 在 EasiCamera 启动约 25 秒后停止接受通知
//      （其 _needNotify 定时器硬编码），因此仅启动初期有效，运行期请用 UIA 模式。
//   3) probe 模式输出窗口全部可自动化元素（异常诊断用）。
//
// 编译（Windows 自带 .NET Framework 4.x csc）：
//   csc.exe /nologo /target:exe /platform:anycpu /optimize+
//           /r:<WPF>\UIAutomationClient.dll /r:<WPF>\UIAutomationTypes.dll /r:<WPF>\WindowsBase.dll
//           /out:EasiCameraTrigger.exe EasiCameraTrigger.cs
//   其中 <WPF> = C:\Windows\Microsoft.NET\Framework64\v4.0.30319\WPF
//
// 输出：单行 JSON 到 stdout；退出码 0=成功，2=找不到窗口/按钮，3=执行失败，4=参数错误。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.Remoting;
using System.Runtime.Remoting.Channels;
using System.Runtime.Remoting.Channels.Ipc;
using System.Text;
using System.Threading;
using System.Windows.Automation;

namespace InspireCameraTools
{
    internal static class Program
    {
        private const string RemotingPort = "e3950283-80cf-4a97-a569-e6110b6e9b82";
        private const string RemotingObject = "RemotingNotifyCamera";

        private static int Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;
            string mode = args.Length > 0 ? args[0].ToLowerInvariant() : "capture";
            var opts = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            for (int i = 1; i < args.Length; i++)
            {
                string a = args[i];
                if (a.StartsWith("--"))
                {
                    string key = a.Substring(2);
                    string val = i + 1 < args.Length && !args[i + 1].StartsWith("--") ? args[++i] : "1";
                    opts[key] = val;
                }
            }
            try
            {
                switch (mode)
                {
                    case "probe":
                        return Probe(opts);
                    case "capture":
                        return Capture(opts);
                    case "remoting":
                        return RemotingNotify(opts);
                    default:
                        Console.WriteLine("{\"ok\":false,\"error\":\"unknown mode: " + Json(mode) + "\"}");
                        return 4;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("{\"ok\":false,\"error\":" + Json(ex.GetType().Name + ": " + ex.Message) + "}");
                return 3;
            }
        }

        // ---------------------------------------------------------------- probe

        private static int Probe(Dictionary<string, string> opts)
        {
            bool raw = opts.ContainsKey("raw");
            var sb = new StringBuilder();
            sb.Append("{\"ok\":true,\"mode\":\"probe\",\"raw\":").Append(raw ? "true" : "false").Append(",\"processes\":[");
            List<IntPtr> windows = new List<IntPtr>();
            var procs = Process.GetProcessesByName("EasiCamera");
            bool first = true;
            foreach (Process p in procs)
            {
                try
                {
                    if (p.MainWindowHandle == IntPtr.Zero) continue;
                    if (!first) sb.Append(',');
                    first = false;
                    sb.Append("{\"pid\":").Append(p.Id).Append(",\"title\":").Append(Json(p.MainWindowTitle)).Append('}');
                    windows.Add(p.MainWindowHandle);
                }
                catch { }
                finally { p.Dispose(); }
            }
            sb.Append("],\"windows\":[");
            for (int w = 0; w < windows.Count; w++)
            {
                AutomationElement win = AutomationElement.FromHandle(windows[w]);
                if (w > 0) sb.Append(',');
                sb.Append("{\"name\":").Append(Json(win.Current.Name)).Append(",\"elements\":[");
                bool firstEl = true;
                if (raw)
                {
                    WalkRaw(win, sb, ref firstEl, 0, 12);
                }
                else
                {
                    AutomationElementCollection all = win.FindAll(TreeScope.Descendants, Condition.TrueCondition);
                    foreach (AutomationElement el in all)
                    {
                        string info = ElementJson(el);
                        if (info == null) continue;
                        if (!firstEl) sb.Append(',');
                        firstEl = false;
                        sb.Append(info);
                    }
                }
                sb.Append("]}");
            }
            sb.Append("]}");
            Console.WriteLine(sb.ToString());
            return windows.Count > 0 ? 0 : 2;
        }

        private static void WalkRaw(AutomationElement parent, StringBuilder sb, ref bool firstEl, int depth, int maxDepth)
        {
            if (depth > maxDepth) return;
            TreeWalker walker = TreeWalker.RawViewWalker;
            AutomationElement child = walker.GetFirstChild(parent);
            while (child != null)
            {
                try
                {
                    string info = ElementJson(child);
                    if (info != null)
                    {
                        if (!firstEl) sb.Append(',');
                        firstEl = false;
                        sb.Append(info);
                    }
                }
                catch { }
                WalkRaw(child, sb, ref firstEl, depth + 1, maxDepth);
                try { child = walker.GetNextSibling(child); }
                catch { break; }
            }
        }

        private static string ElementJson(AutomationElement el)
        {
            try
            {
                AutomationElement.AutomationElementInformation c = el.Current;
                string name = c.Name ?? "";
                string aid = c.AutomationId ?? "";
                string type = c.ControlType == null ? "" : c.ControlType.ProgrammaticName.Replace("ControlType.", "");
                if (name.Length == 0 && aid.Length == 0 && type != "Button") return null;
                string patterns = "";
                try
                {
                    AutomationPattern[] ps = el.GetSupportedPatterns();
                    if (ps != null)
                        foreach (AutomationPattern pt in ps)
                            patterns += pt.ProgrammaticName.Replace("PatternIdentifiers.Pattern", "").Replace("PatternIdentifiers.", "") + ",";
                }
                catch { }
                string rect = "";
                try
                {
                    System.Windows.Rect r = c.BoundingRectangle;
                    rect = (int)r.X + "," + (int)r.Y + "," + (int)r.Width + "," + (int)r.Height;
                }
                catch { }
                return "{\"type\":" + Json(type) + ",\"name\":" + Json(name) + ",\"automationId\":" + Json(aid)
                    + ",\"className\":" + Json(c.ClassName ?? "") + ",\"enabled\":" + (c.IsEnabled ? "true" : "false")
                    + ",\"offscreen\":" + (c.IsOffscreen ? "true" : "false") + ",\"rect\":" + Json(rect)
                    + ",\"patterns\":" + Json(patterns) + "}";
            }
            catch
            {
                return null;
            }
        }

        // --------------------------------------------------------------- capture

        private static int Capture(Dictionary<string, string> opts)
        {
            bool dryRun = opts.ContainsKey("dry-run");
            int waitMs = 0;
            if (opts.ContainsKey("wait-ms")) int.TryParse(opts["wait-ms"], out waitMs);
            if (!WaitForWindow(waitMs))
            {
                Console.WriteLine("{\"ok\":false,\"mode\":\"capture\",\"error\":\"EasiCamera window not found\"}");
                return 2;
            }

            var candidates = new List<Candidate>();
            var procs = Process.GetProcessesByName("EasiCamera");
            foreach (Process p in procs)
            {
                try
                {
                    if (p.MainWindowHandle == IntPtr.Zero) continue;
                    AutomationElement win = AutomationElement.FromHandle(p.MainWindowHandle);
                    AutomationElementCollection all = win.FindAll(TreeScope.Descendants, Condition.TrueCondition);
                    foreach (AutomationElement el in all)
                    {
                        Candidate cand = Score(el);
                        if (cand != null) candidates.Add(cand);
                    }
                }
                catch { }
                finally { p.Dispose(); }
            }
            // 控制视图拿不到文字时，用 Raw 视图的文字节点反查可 Invoke 的按钮祖先
            foreach (Process p in Process.GetProcessesByName("EasiCamera"))
            {
                try
                {
                    if (p.MainWindowHandle == IntPtr.Zero) continue;
                    AutomationElement win = AutomationElement.FromHandle(p.MainWindowHandle);
                    foreach (AutomationElement node in CollectRawElements(win))
                    {
                        string nodeName = "";
                        string nodeType = "";
                        try
                        {
                            nodeName = node.Current.Name ?? "";
                            nodeType = node.Current.ControlType == null ? "" : node.Current.ControlType.ProgrammaticName;
                        }
                        catch { continue; }
                        if (!nodeType.Contains("Text")) continue;
                        string normalized = NormalizeName(nodeName);
                        if (normalized.Length == 0) continue;
                        bool excluded = false;
                        foreach (string bad in ExcludeHints)
                            if (normalized.Contains(bad)) { excluded = true; break; }
                        if (excluded) continue;
                        int textScore = 0;
                        for (int i = 0; i < NameHints.Length; i++)
                        {
                            string hint = NormalizeName(NameHints[i]);
                            if (normalized == hint) { textScore = 240 - i * 10; break; }
                        }
                        if (textScore == 0)
                        {
                            for (int i = 0; i < NameHints.Length; i++)
                            {
                                string hint = NormalizeName(NameHints[i]);
                                if (hint.Length >= 2 && normalized.Contains(hint)) { textScore = 130 - i * 5; break; }
                            }
                        }
                        if (textScore == 0) continue;
                        string ancPatterns;
                        AutomationElement button = FindInvokableAncestor(node, out ancPatterns);
                        if (button == null) continue;
                        string buttonAid = "";
                        try { buttonAid = button.Current.AutomationId ?? ""; } catch { }
                        candidates.Add(new Candidate
                        {
                            Score = textScore + 20,
                            Name = nodeName,
                            AutomationId = buttonAid,
                            ControlType = "Text->Button",
                            Patterns = ancPatterns,
                            Enabled = true,
                            Element = button
                        });
                    }
                }
                catch { }
                finally { p.Dispose(); }
            }
            // 去重（同一个按钮可能被控制视图与 raw 视图各命中一次）
            var dedup = new List<Candidate>();
            var seen = new HashSet<int>();
            foreach (Candidate c in candidates)
            {
                int hash = 0;
                try
                {
                    System.Windows.Rect r = c.Element.Current.BoundingRectangle;
                    hash = ((int)r.X * 397) ^ (int)r.Y;
                }
                catch { hash = c.Element.GetHashCode(); }
                if (!seen.Add(hash)) continue;
                dedup.Add(c);
            }
            candidates = dedup;
            candidates.Sort(delegate (Candidate a, Candidate b) { return a.Score == b.Score ? string.CompareOrdinal(a.Name, b.Name) : b.Score - a.Score; });

            if (candidates.Count == 0)
            {
                Console.WriteLine("{\"ok\":false,\"mode\":\"capture\",\"error\":\"capture button not found in EasiCamera window\",\"candidates\":[]}");
                return 2;
            }
            Candidate best = candidates[0];
            var sb = new StringBuilder();
            if (dryRun)
            {
                sb.Append("{\"ok\":true,\"mode\":\"capture\",\"dryRun\":true,\"method\":\"uia-candidate\",\"element\":")
                  .Append(best.ToJson()).Append(",\"candidates\":").Append(ListJson(candidates)).Append('}');
                Console.WriteLine(sb.ToString());
                return 0;
            }

            string method = null;
            string error = null;
            bool invoked = TryInvoke(best.Element, out method, out error);
            sb.Append("{\"ok\":").Append(invoked ? "true" : "false");
            sb.Append(",\"mode\":\"capture\",\"method\":").Append(Json(method ?? ""));
            sb.Append(",\"element\":").Append(best.ToJson());
            if (error != null) sb.Append(",\"error\":").Append(Json(error));
            if (!invoked) sb.Append(",\"candidates\":").Append(ListJson(candidates));
            sb.Append('}');
            Console.WriteLine(sb.ToString());
            return invoked ? 0 : 3;
        }

        private static bool TryInvoke(AutomationElement el, out string method, out string error)
        {
            error = null;
            method = null;
            AutomationElement target = el;
            string ancPatterns;
            object directPattern;
            bool directInvokable = false;
            try { directInvokable = el.TryGetCurrentPattern(InvokePattern.Pattern, out directPattern); }
            catch { directInvokable = false; }
            if (!directInvokable)
            {
                AutomationElement ancestor = FindInvokableAncestor(el, out ancPatterns);
                if (ancestor != null) target = ancestor;
            }
            try
            {
                object pattern;
                if (target.TryGetCurrentPattern(InvokePattern.Pattern, out pattern))
                {
                    ((InvokePattern)pattern).Invoke();
                    method = "uia-invoke";
                    return true;
                }
            }
            catch (Exception ex)
            {
                error = "invoke: " + ex.Message;
            }
            try
            {
                System.Windows.Rect r = el.Current.BoundingRectangle;
                if (r.Width > 0 && r.Height > 0)
                {
                    ClickAt((int)(r.X + r.Width / 2), (int)(r.Y + r.Height / 2));
                    method = "mouse-click-fallback";
                    return true;
                }
                error = (error == null ? "" : error + "; ") + "empty bounding rect";
            }
            catch (Exception ex)
            {
                error = (error == null ? "" : error + "; ") + "mouse: " + ex.Message;
            }
            return false;
        }

        private static bool WaitForWindow(int waitMs)
        {
            int waited = 0;
            while (true)
            {
                foreach (Process p in Process.GetProcessesByName("EasiCamera"))
                {
                    try
                    {
                        if (p.MainWindowHandle != IntPtr.Zero) return true;
                    }
                    catch { }
                    finally { p.Dispose(); }
                }
                if (waited >= waitMs) return false;
                Thread.Sleep(200);
                waited += 200;
            }
        }

        private sealed class Candidate
        {
            public int Score;
            public string Name;
            public string AutomationId;
            public string ControlType;
            public string Patterns;
            public bool Enabled;
            public AutomationElement Element;

            public string ToJson()
            {
                return "{\"name\":" + Json(Name) + ",\"automationId\":" + Json(AutomationId)
                    + ",\"type\":" + Json(ControlType) + ",\"score\":" + Score
                    + ",\"enabled\":" + (Enabled ? "true" : "false") + "}";
            }
        }

        private static string ListJson(List<Candidate> list)
        {
            var sb = new StringBuilder("[");
            int n = 0;
            foreach (Candidate c in list)
            {
                if (n++ >= 8) break;
                if (n > 1) sb.Append(',');
                sb.Append(c.ToJson());
            }
            return sb.Append(']').ToString();
        }

        /// <summary>递归收集 Raw 视图全部元素（工具栏按钮文字是 TextBlock，控制视图里是空名字）。
        /// 注意：必须用 RawViewWalker —— 控制视图下 DisplayToolBar 的自定义按钮 Name 为空。</summary>
        private static List<AutomationElement> CollectRawElements(AutomationElement root)
        {
            var result = new List<AutomationElement>();
            try
            {
                TreeWalker walker = TreeWalker.RawViewWalker;
                WalkRawCollect(walker, root, result, 0, 16);
            }
            catch { }
            return result;
        }

        private static void WalkRawCollect(TreeWalker walker, AutomationElement parent, List<AutomationElement> result, int depth, int maxDepth)
        {
            if (depth > maxDepth) return;
            AutomationElement child;
            try { child = walker.GetFirstChild(parent); }
            catch { return; }
            while (child != null)
            {
                result.Add(child);
                WalkRawCollect(walker, child, result, depth + 1, maxDepth);
                try { child = walker.GetNextSibling(child); }
                catch { break; }
            }
        }

        /// <summary>从文字节点向上找可 Invoke 的按钮祖先（Raw 视图）。</summary>
        private static AutomationElement FindInvokableAncestor(AutomationElement el, out string patterns)
        {
            patterns = "";
            AutomationElement current = el;
            for (int i = 0; i < 10 && current != null; i++)
            {
                try
                {
                    string ps = "";
                    AutomationPattern[] supported = current.GetSupportedPatterns();
                    if (supported != null)
                        foreach (AutomationPattern pt in supported)
                            ps += pt.ProgrammaticName + ",";
                    if (ps.Contains("InvokePattern"))
                    {
                        patterns = ps;
                        return current;
                    }
                    current = TreeWalker.RawViewWalker.GetParent(current);
                }
                catch { return null; }
            }
            return null;
        }

        private static string NormalizeName(string name)
        {
            if (string.IsNullOrEmpty(name)) return "";
            var sb = new StringBuilder();
            foreach (char ch in name.Trim().ToLowerInvariant())
            {
                if (ch == ' ' || ch == '\t' || ch == '\u3000') continue;
                sb.Append(ch);
            }
            return sb.ToString();
        }

        private static readonly string[] NameHints = new string[] { "拍照", "take photo", "takephoto", "take_photo", "拍摄", "capture", "photo", "snapshot" };
        private static readonly string[] IdHints = new string[] { "takephoto", "take_photo", "capture", "snapshot" };
        private static readonly string[] ExcludeHints = new string[] { "延时", "连拍", "timelapse", "time lapse", "预览", "preview" };

        private static Candidate Score(AutomationElement el)
        {
            try
            {
                AutomationElement.AutomationElementInformation c = el.Current;
                string name = (c.Name ?? "").Trim();
                string aid = (c.AutomationId ?? "");
                string type = c.ControlType == null ? "" : c.ControlType.ProgrammaticName;
                string patterns = "";
                try
                {
                    AutomationPattern[] ps = el.GetSupportedPatterns();
                    if (ps != null)
                        foreach (AutomationPattern p in ps)
                            patterns += p.ProgrammaticName + ",";
                }
                catch { }
                bool invokable = patterns.Contains("InvokePattern");
                bool buttonish = type.IndexOf("Button", StringComparison.OrdinalIgnoreCase) >= 0;
                if (!invokable && !buttonish) return null;
                string lowerName = name.ToLowerInvariant();
                string lowerAid = aid.ToLowerInvariant();
                string lowered = (name + " " + aid).ToLowerInvariant();
                foreach (string bad in ExcludeHints)
                    if (lowered.Contains(bad)) return null;

                int score = 0;
                for (int i = 0; i < NameHints.Length; i++)
                {
                    if (lowerName == NameHints[i])
                    {
                        score = 200 - i * 10;
                        break;
                    }
                }
                if (score == 0)
                {
                    for (int i = 0; i < NameHints.Length; i++)
                    {
                        if (lowerName.Contains(NameHints[i]))
                        {
                            score = 120 - i * 10;
                            break;
                        }
                    }
                }
                if (score == 0)
                {
                    for (int i = 0; i < IdHints.Length; i++)
                    {
                        if (lowerAid.Contains(IdHints[i]))
                        {
                            score = 90 - i * 5;
                            break;
                        }
                    }
                }
                if (score == 0) return null;
                if (!invokable) score -= 40;
                if (!invokable) return null;
                if (!name.StartsWith("拍照") && !lowerName.StartsWith("take photo")) score -= 5;
                if (buttonish) score += 10;
                return new Candidate
                {
                    Score = score,
                    Name = name,
                    AutomationId = aid,
                    ControlType = type.Replace("ControlType.", ""),
                    Patterns = patterns,
                    Enabled = c.IsEnabled,
                    Element = el
                };
            }
            catch
            {
                return null;
            }
        }

        // -------------------------------------------------------------- remoting

        private static int RemotingNotify(Dictionary<string, string> opts)
        {
            int pid, vid;
            string message = opts.ContainsKey("message") ? opts["message"] : "Key5";
            if (!opts.ContainsKey("pid") || !opts.ContainsKey("vid")
                || !int.TryParse(opts["pid"], NumberStyles.Integer, CultureInfo.InvariantCulture, out pid)
                || !int.TryParse(opts["vid"], NumberStyles.Integer, CultureInfo.InvariantCulture, out vid))
            {
                Console.WriteLine("{\"ok\":false,\"mode\":\"remoting\",\"error\":\"--pid and --vid are required\"}");
                return 4;
            }
            bool ok = false;
            string error = null;
            try
            {
                ChannelServices.RegisterChannel(new IpcClientChannel(), false);
            }
            catch (Exception ex)
            {
                error = "register channel: " + ex.Message;
            }
            if (error == null)
            {
                // 本 exe 自身承载代理类型：Remoting 按程序集限定名解析类型时，
                // 对当前可执行文件（Version=0.0.0.0）可能解析不到，这里显式兜底。
                AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs e)
                {
                    if (e.Name != null && e.Name.StartsWith("EasiCameraTrigger", StringComparison.OrdinalIgnoreCase))
                        return typeof(Program).Assembly;
                    return null;
                };
                try
                {
                    string url = "Ipc://" + RemotingPort + "/" + RemotingObject;
                    object remote = Activator.GetObject(typeof(EasiCamera.Communication.Remoting.RemotingNotifyCamera), url);
                    EasiCamera.Communication.Remoting.RemotingNotifyCamera proxy =
                        (EasiCamera.Communication.Remoting.RemotingNotifyCamera)remote;
                    ok = proxy.Notify(pid, vid, message);
                }
                catch (RemotingException ex)
                {
                    error = "remoting: " + ex.Message;
                }
                catch (Exception ex)
                {
                    error = ex.GetType().Name + ": " + ex.Message;
                }
            }
            var sb = new StringBuilder();
            sb.Append("{\"ok\":").Append(ok ? "true" : "false");
            sb.Append(",\"mode\":\"remoting\",\"pid\":").Append(pid).Append(",\"vid\":").Append(vid)
              .Append(",\"message\":").Append(Json(message));
            if (error != null) sb.Append(",\"error\":").Append(Json(error));
            sb.Append('}');
            Console.WriteLine(sb.ToString());
            return ok ? 0 : 3;
        }

        // ------------------------------------------------------------- utilities

        private static void ClickAt(int x, int y)
        {
            NativeMethods.SetCursorPos(x, y);
            Thread.Sleep(30);
            NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTDOWN, x, y, 0, UIntPtr.Zero);
            Thread.Sleep(30);
            NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTUP, x, y, 0, UIntPtr.Zero);
            Thread.Sleep(60);
        }

        private static string Json(string s)
        {
            var sb = new StringBuilder("\"");
            if (s == null) return "null";
            foreach (char ch in s)
            {
                switch (ch)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (ch < 0x20) sb.Append("\\u").Append(((int)ch).ToString("x4"));
                        else sb.Append(ch);
                        break;
                }
            }
            return sb.Append('"').ToString();
        }

        private static class NativeMethods
        {
            [System.Runtime.InteropServices.DllImport("user32.dll")]
            public static extern bool SetCursorPos(int x, int y);
            [System.Runtime.InteropServices.DllImport("user32.dll")]
            public static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, UIntPtr dwExtraInfo);
            public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
            public const uint MOUSEEVENTF_LEFTUP = 0x0004;
        }
    }
}
