# -*- coding: utf-8 -*-
"""
Time Slider Bookmark Bar - Drag & Drop installer for Maya.

使い方 / How to install:
    1. このリポジトリ(ZIP)をどこでもよいので解凍してください。
       Unzip this repository anywhere (a temp folder / Downloads is fine).
    2. Maya のビューポートに、この install.py をドラッグ＆ドロップしてください。
       Drag & drop this install.py into the Maya viewport.
    3. [Install] を押すとシェルフボタンが追加されます。
       Click [Install]; a shelf button is added.
    4. インストール後は、解凍したフォルダも ZIP も削除して構いません。
       After installing you may delete the unzipped folder AND the ZIP.

やっていること / What it does:
    - ツール本体(scripts/ と icons/)を Maya のユーザーフォルダ配下
        <maya>/modules/TimeSliderBookmarkBar/  へ **コピー** します（自己完結）。
      Copies the tool (scripts/ and icons/) INTO the Maya user directory, so it
      no longer depends on the folder you unzipped.
    - Maya モジュール(.mod)を <maya>/modules/TimeSliderBookmarkBar.mod に作成し、
      コピー先を参照します（再起動後も有効）。
    - 現在のシェルフに起動ボタンを追加します。
"""

import os
import sys
import shutil

TOOL_NAME = "TimeSliderBookmarkBar"
VERSION = "1.0.1"


def onMayaDroppedPythonFile(*args):
    """Maya がドラッグ＆ドロップ時に呼び出すエントリポイント。"""
    import maya.cmds as cmds
    import maya.mel as mel

    src_root = os.path.dirname(os.path.abspath(__file__))
    dst_root = _dest_root(cmds)

    ans = cmds.confirmDialog(
        title=TOOL_NAME,
        message=(u"Time Slider Bookmark Bar をインストールしますか？\n"
                 u"(Maya ユーザーフォルダへコピー ＋ モジュール登録 ＋ シェルフボタン)\n\n"
                 u"インストール先:\n%s\n\n"
                 u"※インストール後は、解凍フォルダも ZIP も削除して構いません。"
                 % dst_root),
        button=["Install", "Cancel"],
        defaultButton="Install", cancelButton="Cancel", dismissString="Cancel")
    if ans != "Install":
        return

    # 1) ツール本体をユーザーフォルダへコピー（自己完結 = 解凍元を消してもOK）
    try:
        _install_files(src_root, dst_root)
    except Exception as e:
        cmds.warning(u"ファイルのコピーに失敗: %s" % e)
        return

    scripts = os.path.join(dst_root, "scripts")

    # 2) 現在のセッションで即使えるように（コピー先をパスに追加）
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    # 3) 再起動後も有効になるよう Maya モジュール(.mod)を作成（コピー先を参照）
    try:
        _write_module(cmds, dst_root)
    except Exception as e:
        cmds.warning(u"module(.mod) の作成に失敗: %s" % e)

    # 4) シェルフボタン
    try:
        _make_shelf_button(cmds, mel, dst_root)
    except Exception as e:
        cmds.warning(u"シェルフボタン作成に失敗: %s" % e)

    try:
        cmds.inViewMessage(
            amg=u"<hl>Time Slider Bookmark Bar</hl> installed. "
                u"シェルフのボタンから起動できます（解凍フォルダは削除可）。",
            pos="midCenter", fade=True)
    except Exception:
        pass
    print("# %s %s installed to: %s" % (TOOL_NAME, VERSION, dst_root))


def _dest_root(cmds):
    """コピー先(自己完結の恒久フォルダ) = <maya userAppDir>/modules/TimeSliderBookmarkBar"""
    user_app = cmds.internalVar(userAppDir=True)
    return os.path.join(user_app, "modules", TOOL_NAME)


def _install_files(src_root, dst_root):
    """scripts/ と icons/ を dst_root へコピーする（既存は上書き）。"""
    if os.path.abspath(src_root) == os.path.abspath(dst_root):
        return  # 既にコピー先から実行している
    for sub in ("scripts", "icons"):
        s = os.path.join(src_root, sub)
        if os.path.isdir(s):
            _copy_tree(s, os.path.join(dst_root, sub))
    # 参考ドキュメントも任意でコピー（無くても動作）
    for name in ("README.md", "LICENSE"):
        s = os.path.join(src_root, name)
        if os.path.isfile(s):
            if not os.path.isdir(dst_root):
                os.makedirs(dst_root)
            shutil.copy2(s, os.path.join(dst_root, name))


def _copy_tree(src, dst):
    """Python2/3 両対応の再帰コピー（上書き）。"""
    if not os.path.isdir(dst):
        os.makedirs(dst)
    for name in os.listdir(src):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            _copy_tree(s, d)
        else:
            try:
                if os.path.exists(d):
                    os.chmod(d, 0o666)
            except Exception:
                pass
            shutil.copy2(s, d)


def _write_module(cmds, dst_root):
    modules_dir = os.path.join(cmds.internalVar(userAppDir=True), "modules")
    if not os.path.isdir(modules_dir):
        os.makedirs(modules_dir)
    mod_path = os.path.join(modules_dir, TOOL_NAME + ".mod")
    root_fwd = dst_root.replace("\\", "/")
    with open(mod_path, "w") as f:
        f.write("+ %s %s %s\n" % (TOOL_NAME, VERSION, root_fwd))
        f.write("scripts: scripts\n")
        f.write("icons: icons\n")


def _make_shelf_button(cmds, mel, dst_root):
    icon = os.path.join(dst_root, "icons", "shelf_icon.png").replace("\\", "/")
    if not os.path.exists(icon):
        icon = "menuIconWindow.png"
    command = (
        "import timeslider_bookmark_labels as tsbl\n"
        "try:\n"
        "    import importlib\n"
        "    importlib.reload(tsbl)\n"
        "except Exception:\n"
        "    pass\n"
        "tsbl.show_controls()"
    )
    kwargs = dict(
        image=icon,
        label="BMBar",
        imageOverlayLabel="BM",
        annotation="Time Slider Bookmark Bar",
        command=command,
        sourceType="python",
    )

    # 既存の BMBar ボタンがあれば「更新」する（再インストールで増やさない）。
    # 過去のインストールで重複してしまっていた場合は、先頭を残して余分を削除する。
    existing = _find_shelf_buttons(cmds, mel)
    if existing:
        try:
            cmds.shelfButton(existing[0], e=True, **kwargs)
        except Exception:
            pass
        for extra in existing[1:]:
            try:
                cmds.deleteUI(extra)
            except Exception:
                pass
        return

    # 無ければ現在のシェルフに新規作成
    parent = None
    try:
        top = mel.eval("$_tsbl_tmp = $gShelfTopLevel")
        parent = cmds.tabLayout(top, q=True, selectTab=True)
    except Exception:
        parent = None
    if parent:
        cmds.shelfButton(parent=parent, **kwargs)
    else:
        cmds.shelfButton(**kwargs)


def _find_shelf_buttons(cmds, mel):
    """全シェルフを走査し、本ツールの起動ボタンを特定して返す（重複作成の防止・更新用）。

    判定基準: コマンドに 'timeslider_bookmark_labels' を含む、
              または annotation が 'Time Slider Bookmark Bar'。
    """
    found = []
    try:
        top = mel.eval("$_tsbl_tmp = $gShelfTopLevel")
        shelves = cmds.tabLayout(top, q=True, childArray=True) or []
    except Exception:
        shelves = []
    for shelf in shelves:
        try:
            btns = cmds.shelfLayout(shelf, q=True, childArray=True) or []
        except Exception:
            btns = []
        for btn in btns:
            try:
                if cmds.objectTypeUI(btn) != "shelfButton":
                    continue
                cmd = cmds.shelfButton(btn, q=True, command=True) or ""
                ann = cmds.shelfButton(btn, q=True, annotation=True) or ""
                if "timeslider_bookmark_labels" in cmd or ann == "Time Slider Bookmark Bar":
                    found.append(btn)
            except Exception:
                pass
    return found


if __name__ == "__main__":
    # スクリプトエディタから実行した場合もインストールできるように
    try:
        onMayaDroppedPythonFile()
    except Exception as e:
        print("Run inside Maya. (%s)" % e)
