# -*- coding: utf-8 -*-
"""命令行入口（契约 §3.3 的 CLI 等价物）。

在 ``InspireCameraTools/`` 目录下运行::

    python -m core.cli detect --main <Main目录> [--json]
    python -m core.cli list [--version 2.0.10.4229] [--main <Main目录>] [--json]
    python -m core.cli plan   --main <Main目录> --features remove_ocr,disable_ai_key [--json]
    python -m core.cli apply  --main <Main目录> --features ... [--backup-root <目录>] [--json]
    python -m core.cli restore --main <Main目录> --backup <备份目录> [--json]
    python -m core.cli find   [--explicit <目录>] [--json]
    python -m core.cli validate [--json]

退出码：0 成功；1 操作失败/未识别；2 参数错误。
app 不依赖本 CLI；它只是供开发/规则作者手工验证。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional, Sequence

from . import APP_NAME, __version__


def _json_dump(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _split_features(text: Optional[str]) -> list[str]:
    """解析 --features：支持逗号/中文逗号/分号/空格分隔。"""
    if not text:
        return []
    normalized = str(text)
    for sep in ("，", ",", "；", ";", " ", "\t", "\n"):
        normalized = normalized.replace(sep, " ")
    return [part for part in normalized.split(" ") if part]


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", dest="json", action="store_true", default=None,
                       help="以 JSON 格式输出（便于脚本消费）")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m core.cli",
        description="%s 补丁引擎命令行（%s）" % (APP_NAME, __version__),
    )
    _add_common(parser)
    subparsers = parser.add_subparsers(dest="command")

    detect = subparsers.add_parser("detect", help="识别 Main 目录的 EasiCamera 版本")
    detect.add_argument("--main", default=None, help="EasiCamera 的 Main 目录")
    detect.add_argument("--auto", action="store_true", help="自动搜索安装目录（忽略 --main）")
    _add_common(detect)

    lst = subparsers.add_parser("list", help="列出已发现版本 / 某版本的功能可用性")
    lst.add_argument("--version", default=None, help="版本号，如 2.0.10.4229")
    lst.add_argument("--main", default=None, help="可选：给出 Main 目录以显示「是否已打补丁」")
    _add_common(lst)

    plan_cmd = subparsers.add_parser("plan", help="dry-run：显示所选功能的可用性与操作说明（不写盘）")
    plan_cmd.add_argument("--main", required=True, help="EasiCamera 的 Main 目录")
    plan_cmd.add_argument("--features", required=True, help="功能 ID，逗号分隔（见 list）")
    _add_common(plan_cmd)

    apply_cmd = subparsers.add_parser("apply", help="应用所选补丁（先校验、备份、原子写回）")
    apply_cmd.add_argument("--main", required=True, help="EasiCamera 的 Main 目录")
    apply_cmd.add_argument("--features", required=True, help="功能 ID，逗号分隔")
    apply_cmd.add_argument("--backup-root", default=None,
                           help="备份根目录（默认 <Main>/../_InspirePatchBackup）")
    _add_common(apply_cmd)

    restore = subparsers.add_parser("restore", help="从备份目录恢复原版文件")
    restore.add_argument("--main", required=True, help="EasiCamera 的 Main 目录")
    restore.add_argument("--backup", required=True, help="备份目录（apply 输出里的 backup_dir）")
    _add_common(restore)

    find = subparsers.add_parser("find", help="查找 EasiCamera 安装的 Main 目录")
    find.add_argument("--explicit", default=None, help="指定目录（Main 或其父目录）")
    _add_common(find)

    validate = subparsers.add_parser("validate", help="校验所有已发现规则文件格式（规则作者自检）")
    _add_common(validate)
    return parser


# --------------------------------------------------------------------------- #
# 各子命令
# --------------------------------------------------------------------------- #


def _print_rule_load_errors(engine_rules_module) -> None:
    errors = engine_rules_module.load_errors()
    if not errors:
        return
    print("[警告] %d 个规则模块加载失败：" % len(errors))
    for item in errors:
        print("  - %s: %s" % (item.get("module"), item.get("error")))


def cmd_detect(args: argparse.Namespace) -> int:
    from . import patch_engine, rules

    main_dir = patch_engine.find_main_dir(None if args.auto else args.main)
    payload: dict = {"ok": False, "main_dir": main_dir, "detected": None}
    if main_dir is None:
        payload["message"] = "未找到 EasiCamera 安装目录（可用 --main 指定）"
        if args.json:
            _json_dump(payload)
        else:
            print(payload["message"])
        return 1
    detected = patch_engine.detect_version(main_dir)
    if detected is None:
        payload["message"] = "无法识别版本：Main 目录不匹配任何规则指纹"
        if args.json:
            _json_dump(payload)
        else:
            print("检测目录: %s" % main_dir)
            print(payload["message"])
            _print_rule_load_errors(rules)
        return 1

    version = detected.version
    availabilities = patch_engine.list_features(version, main_dir)
    payload.update(
        {
            "ok": True,
            "detected": detected.to_dict(),
            "features": [item.to_dict() for item in availabilities],
            "rule_load_errors": rules.load_errors(),
        }
    )
    if args.json:
        _json_dump(payload)
        return 0
    print("检测目录: %s" % main_dir)
    print("版本: %s（%s）" % (version, detected.display_name))
    total = len(detected.rule.get("files") or {})
    print("指纹匹配: %d/%d 个文件" % (len(detected.matched_files), total))
    for name, digest in sorted(detected.matched_files.items()):
        print("  %-28s %s" % (name, digest))
    print("功能可用性:")
    for item in availabilities:
        if item.already_patched:
            state = "已应用"
        elif item.available:
            state = "可用"
        else:
            state = "不可用"
        print("  [%s] %-20s %s%s" % (
            "x" if item.available else " ",
            item.feature.id,
            state,
            "" if item.available and not item.reason else "（%s）" % (item.reason or ""),
        ))
    _print_rule_load_errors(rules)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from . import patch_engine, rules

    if args.version:
        try:
            availabilities = patch_engine.list_features(args.version, args.main)
        except ValueError as exc:
            message = str(exc)
            if args.json:
                _json_dump({"ok": False, "message": message})
            else:
                print(message)
            return 2
        rule = rules.get_rules(args.version) or {}
        payload = {
            "ok": True,
            "version": args.version,
            "display_name": rule.get("display_name"),
            "main_dir": patch_engine.find_main_dir(args.main) if args.main else None,
            "features": [item.to_dict() for item in availabilities],
        }
        if args.json:
            _json_dump(payload)
            return 0
        print("版本 %s（%s）功能列表：" % (args.version, rule.get("display_name", "")))
        for item in availabilities:
            mark = "已应用" if item.already_patched else ("可用" if item.available else "不可用")
            print("  %-20s %-8s %s" % (item.feature.id, mark, item.feature.name))
            if item.reason:
                print("      %s" % item.reason)
        return 0

    all_rules = rules.all_rules()
    errors = rules.load_errors()
    validate_map = {version: patch_engine.validate_rule(rule) for version, rule in all_rules.items()}
    payload = {
        "ok": not errors,
        "versions": [
            {
                "version": version,
                "display_name": rule.get("display_name"),
                "source_installer": rule.get("source_installer"),
                "features": sorted((rule.get("features") or {}).keys()),
                "files": sorted((rule.get("files") or {}).keys()),
                "errors": validate_map.get(version, []),
            }
            for version, rule in all_rules.items()
        ],
        "rule_load_errors": errors,
    }
    if args.json:
        _json_dump(payload)
        return 0
    if not all_rules:
        print("未发现任何规则文件（core/rules/v2_*.py）")
        _print_rule_load_errors(rules)
        return 1
    print("已发现 %d 个版本规则：" % len(all_rules))
    for version, rule in all_rules.items():
        feature_ids = sorted((rule.get("features") or {}).keys())
        errs = validate_map.get(version, [])
        print("  %-14s %-12s 可用功能: %s" % (
            version,
            rule.get("display_name", ""),
            ", ".join(feature_ids) if feature_ids else "（无）",
        ))
        if errs:
            print("      [规则错误] %s" % "；".join(errs[:3]))
    _print_rule_load_errors(rules)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    from . import patch_engine

    feature_ids = _split_features(args.features)
    if not feature_ids:
        print("--features 不能为空")
        return 2
    main_dir = patch_engine.find_main_dir(args.main)
    if main_dir is None:
        message = "安装目录无效或不存在: %s" % args.main
        if args.json:
            _json_dump({"ok": False, "message": message})
        else:
            print(message)
        return 1
    try:
        items = patch_engine.plan(main_dir, feature_ids)
    except KeyError as exc:
        message = "功能 ID 无效: %s" % exc
        if args.json:
            _json_dump({"ok": False, "message": message})
        else:
            print(message)
        return 2
    detected = patch_engine.detect_version(main_dir)
    payload = {
        "ok": detected is not None,
        "main_dir": main_dir,
        "detected": detected.to_dict() if detected else None,
        "items": [item.to_dict() for item in items],
    }
    if args.json:
        _json_dump(payload)
        return 0 if detected else 1
    print("dry-run 计划（不写盘）—— 目录: %s" % main_dir)
    if detected is None:
        print("无法识别版本：Main 目录不匹配任何规则指纹")
    else:
        print("版本: %s（%s）" % (detected.version, detected.display_name))
    for item in items:
        mark = "已应用" if item.already_patched else ("可应用" if item.available else "不可用")
        print("\n  [%s] %s  %s" % (item.feature.id, mark, item.feature.name))
        if item.reason:
            print("      原因: %s" % item.reason)
        for op in item.ops:
            print("      - %s @ %s（%d 字节）%s" % (op["file"], op["offset"], op["length"], op["note"]))
    return 0 if detected else 1


def cmd_apply(args: argparse.Namespace) -> int:
    from . import patch_engine

    feature_ids = _split_features(args.features)
    if not feature_ids:
        print("--features 不能为空")
        return 2
    main_dir = patch_engine.find_main_dir(args.main)
    if main_dir is None:
        message = "安装目录无效或不存在: %s" % args.main
        if args.json:
            _json_dump({"ok": False, "message": message})
        else:
            print(message)
        return 1
    try:
        result = patch_engine.apply_patches(main_dir, feature_ids, args.backup_root)
    except KeyError as exc:
        message = "功能 ID 无效: %s" % exc
        if args.json:
            _json_dump({"ok": False, "message": message})
        else:
            print(message)
        return 2
    payload = {"ok": result.ok, "main_dir": main_dir, "result": result.to_dict()}
    if args.json:
        _json_dump(payload)
        return 0 if result.ok else 1
    print(payload["result"]["message"])
    if result.applied:
        print("已应用: %s" % ", ".join(result.applied))
    for feature_id, reason in result.failed:
        print("失败 [%s] %s" % (feature_id, reason))
    if result.backup_dir:
        print("备份目录: %s" % result.backup_dir)
    return 0 if result.ok else 1


def cmd_restore(args: argparse.Namespace) -> int:
    from . import patch_engine

    main_dir = patch_engine.find_main_dir(args.main)
    if main_dir is None:
        message = "安装目录无效或不存在: %s" % args.main
        if args.json:
            _json_dump({"ok": False, "message": message})
        else:
            print(message)
        return 1
    result = patch_engine.restore_backup(main_dir, args.backup)
    payload = {"ok": result.ok, "main_dir": main_dir, "backup_dir": result.backup_dir,
               "result": result.to_dict()}
    if args.json:
        _json_dump(payload)
        return 0 if result.ok else 1
    print(result.message)
    for file_name, reason in result.failed:
        print("失败 %s: %s" % (file_name, reason))
    return 0 if result.ok else 1


def cmd_find(args: argparse.Namespace) -> int:
    from . import patch_engine

    main_dir = patch_engine.find_main_dir(args.explicit)
    payload = {"ok": main_dir is not None, "main_dir": main_dir}
    if args.json:
        _json_dump(payload)
        return 0 if main_dir else 1
    if main_dir:
        print(main_dir)
        return 0
    print("未找到 EasiCamera 安装目录" + ("（指定目录无效: %s）" % args.explicit if args.explicit else ""))
    return 1


def cmd_validate(args: argparse.Namespace) -> int:
    from . import patch_engine, rules

    all_rules = rules.all_rules()
    result = patch_engine.validate_all_rules()
    payload = {
        "ok": all(not errors for errors in result.values()),
        "rules": result,
        "rule_load_errors": rules.load_errors(),
    }
    if not all_rules:
        payload["ok"] = False
        payload["message"] = "未发现任何规则文件"
    if args.json:
        _json_dump(payload)
        return 0 if payload["ok"] else 1
    if not all_rules:
        print("未发现任何规则文件")
        return 1
    print("规则文件校验：")
    for version, errors in result.items():
        print("  %-14s %s" % (version, "通过" if not errors else "失败"))
        for error in errors:
            print("      - %s" % error)
    _print_rule_load_errors(rules)
    return 0 if payload["ok"] else 1


_COMMANDS = {
    "detect": cmd_detect,
    "list": cmd_list,
    "plan": cmd_plan,
    "apply": cmd_apply,
    "restore": cmd_restore,
    "find": cmd_find,
    "validate": cmd_validate,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    # --json 可能写在整个命令行最前面（顶层解析器）或子命令后，统一处理
    if getattr(args, "json", None) is None:
        args.json = False
    handler = _COMMANDS[args.command]
    try:
        return handler(args)
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI 兜底：打印中文错误而不是抛栈
        if getattr(args, "json", False):
            _json_dump({"ok": False, "message": "内部错误: %s: %s" % (type(exc).__name__, exc)})
        else:
            print("内部错误: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
            if os.environ.get("INSPIRE_DEBUG"):
                raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
