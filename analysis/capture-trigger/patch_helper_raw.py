import io

p = r'D:\开发\SeewoCamera\InspireCameraTools\assets\bin\EasiCameraTrigger.cs'
s = io.open(p, encoding='utf-8').read()

# 1) 在 ListJson 之后插入 raw 收集与祖先查找工具
anchor = '''        private static readonly string[] NameHints'''
insert = '''        /// <summary>递归收集 Raw 视图全部元素（工具栏按钮文字是 TextBlock，控制视图里是空名字）。
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
                if (ch == ' ' || ch == '\\t' || ch == '\\u3000') continue;
                sb.Append(ch);
            }
            return sb.ToString();
        }

        private static readonly string[] NameHints'''
assert anchor in s
s = s.replace(anchor, insert, 1)

# 2) Capture 中加入 raw 文字候选
old = '''            candidates.Sort(delegate (Candidate a, Candidate b) { return a.Score == b.Score ? string.CompareOrdinal(a.Name, b.Name) : b.Score - a.Score; });'''
new = '''            // 控制视图拿不到文字时，用 Raw 视图的文字节点反查可 Invoke 的按钮祖先
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
            candidates.Sort(delegate (Candidate a, Candidate b) { return a.Score == b.Score ? string.CompareOrdinal(a.Name, b.Name) : b.Score - a.Score; });'''
assert old in s
s = s.replace(old, new, 1)

# 3) TryInvoke：若目标本身不支持 Invoke，再向上找一次
old = '''        private static bool TryInvoke(AutomationElement el, out string method, out string error)
        {
            error = null;
            method = null;
            try
            {
                object pattern;
                if (el.TryGetCurrentPattern(InvokePattern.Pattern, out pattern))
                {
                    ((InvokePattern)pattern).Invoke();
                    method = "uia-invoke";
                    return true;
                }
            }
            catch (Exception ex)
            {
                error = "invoke: " + ex.Message;
            }'''
new = '''        private static bool TryInvoke(AutomationElement el, out string method, out string error)
        {
            error = null;
            method = null;
            AutomationElement target = el;
            string ancPatterns;
            if (!el.TryGetCurrentPattern(InvokePattern.Pattern, out _))
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
            }'''
assert old in s
s = s.replace(old, new, 1)

io.open(p, 'w', encoding='utf-8').write(s)
print('helper raw-text capture matching patched')
