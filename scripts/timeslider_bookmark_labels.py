# -*- coding: utf-8 -*-
"""
Time Slider Bookmark Bar + Label Overlay for Maya
--------------------------------------------------
タイムスライダーの下部に「ブックマーク色で塗った帯」を描き、名前(＋任意でレンジ)を表示。
- 範囲が重複するブックマークは 2段・3段… と縦に積んで表示（レーン配置）
- 帯へのマウスオーバーでフル情報をツールチップ表示
- 帯のダブルクリックでブックマーク名を変更
- 帯の両端(左右)をドラッグして開始/終了フレームを変更
帯の太さ・文字サイズはタイムスライダの高さ(1x/2x/3x/4x)に追従して拡縮する。

■ 使い方（推奨: コントロールUI）
    import timeslider_bookmark_labels as tsbl
    tsbl.show_controls()   # タイムスライダー左隣にUIを表示（バー表示もここでON/OFF）
    tsbl.hide_controls()   # UI・オーバーレイをまとめて消す

    コントロールUI（タイムスライダー左隣に横一列でドッキング）:
        [＋] ブックマーク追加（現在の選択範囲／無ければ再生範囲）
        [バー] バー表示 ON/OFF（ON=発光, OFF=消灯）
        [縦slider] バーサイズ（bar_ratio）
        [縦slider] フォントサイズ（font_ratio）
        [縦slider] アルファ（alpha 0.0-1.0）
        [レンジ] レンジ併記 ON/OFF（ON=発光, OFF=消灯）
      ※縦スライダーの高さ = タイムスライダーの高さ(太さ 1x/2x/3x/4x)に追従

    低レベルAPI（UIを使わず直接オーバーレイを出す場合）:
        tsbl.show_overlay(bar_ratio=0.5, font_ratio=0.6, alpha=0.9, show_range=True)
        tsbl.hide_overlay()

■ 帯（バー）の操作
    - シングルクリック          : ブックマーク名を変更（入力ダイアログ）
    - ダブルクリック            : そのBMの範囲をタイムスライダーの St/Ed に設定
    - 左端/右端をドラッグ        : 開始/終了フレームを変更
    - Ctrl + マウスオーバー→クリック : バー上に ◀ ● ▶ を表示
          ◀ = 一つ前のBMの範囲を St/Ed に設定
          ● = このBMの範囲を St/Ed に設定
          ▶ = 一つ後のBMの範囲を St/Ed に設定
    - Shift + マウスオーバー→クリック : バー上に ◁ ▷ を表示
          ◁ = St だけを「一つ前のBMのStartフレーム」に設定
          ▷ = Ed だけを「一つ後のBMのEndフレーム」に設定
    - 帯の外                    : 通常どおりタイムスライダーのスクラブ

■ 注意
    マウス操作を受けるためオーバーレイのマウス透過を解除しています。
    帯の端ドラッグ／ダブルクリック以外のクリックは下のタイムスライダーへ流す設計です。
    もし帯の上でスクラブが効かない等あれば方式を調整します。

■ タイムスライダの高さ設定
    日本語: ウィンドウ > 設定/プリファレンス > プリファレンス > 設定(タイムスライダ) > 高さ
    英語  : Windows > Settings/Preferences > Preferences > Settings > Height
    ※段組みで上に伸びるため 2x / 3x 推奨
"""

import os
import sys
import base64
import random
import colorsys
from maya import mel, cmds
import maya.OpenMayaUI as omui

# --- PySide2 / PySide6 両対応 -------------------------------------------------
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance


# --- デフォルト値 -------------------------------------------------------------
OBJECT_NAME = "bookmarkLabelOverlay"

MARGIN_L = 12                    # タイムスライダー実描画領域の左インセット(px)。既定はMaya2027基準
MARGIN_R = 12                    # タイムスライダー実描画領域の右インセット(px)。set_inset()で調整可

DEFAULT_BAR_RATIO = 0.42         # 1段あたりの帯の高さ = ウィジェット高さ * この割合
DEFAULT_FONT_RATIO = 0.55        # 文字サイズ = 帯の高さ * この割合
DEFAULT_BOTTOM_RATIO = 0.02      # 下端からの余白 = ウィジェット高さ * この割合
DEFAULT_ALPHA = 0.92            # 帯の不透明度(0.0-1.0)
DEFAULT_SHOW_RANGE = True        # タイムレンジ併記の初期値

MIN_BAR_HEIGHT = 6               # 帯の高さの下限(px)
MIN_FONT_PX = 7                  # 文字サイズの下限(px)

LANE_GAP = 1                     # 段間の隙間(px)
EDGE_PX = 4                      # 端とみなす幅(px)。ここをドラッグで範囲変更
MOVE_THRESHOLD_PX = 3            # 中央をこの距離以上ドラッグしたら「移動」とみなす(px)
LONG_PRESS_MS = 350             # これ以上の長押しはリネームにしない(ms)
DOCK_SNAP_PX = 28               # ドッキング位置にこの距離まで近づけて離すと自動再ドック(px)

ROUND_RADIUS = 2                 # 帯の角丸(px)
REFRESH_MS = 400                 # 再描画間隔(ms)
MIN_LABEL_W = 20                 # この幅未満の範囲は文字を描かない（ツールチップは出る）


_INSTANCE = None                 # 二重起動防止用
_DELETE_MODE = False             # デリートモード（バー左クリックで削除）


def _set_delete_mode(on):
    """デリートモードのON/OFF。バーの左クリック挙動と表示を切り替える。"""
    global _DELETE_MODE
    _DELETE_MODE = bool(on)
    if _INSTANCE is not None:
        try:
            if _DELETE_MODE:
                _INSTANCE.setCursor(QtCore.Qt.PointingHandCursor)
            else:
                _INSTANCE.unsetCursor()
            _INSTANCE.update()
        except Exception:
            pass


# --- 設定の永続化（Maya optionVar。再起動後も保持） -------------------------
_OV = {
    'bar_lo': 'tsblBarLo', 'bar_hi': 'tsblBarHi',
    'font': 'tsblFont', 'alpha': 'tsblAlpha',
    'show_range': 'tsblShowRange', 'bar_on': 'tsblBarOn',
    'inset_l': 'tsblInsetL', 'inset_r': 'tsblInsetR',
}


def _ov_get(key, default=None):
    name = _OV[key]
    try:
        if cmds.optionVar(exists=name):
            return cmds.optionVar(q=name)
    except Exception:
        pass
    return default


def _ov_set(key, value):
    name = _OV[key]
    try:
        if isinstance(value, bool):
            cmds.optionVar(iv=(name, 1 if value else 0))
        elif isinstance(value, int):
            cmds.optionVar(iv=(name, value))
        else:
            cmds.optionVar(fv=(name, float(value)))
    except Exception:
        pass


def _get_timeslider_widget():
    """Mayaのタイムスライダーを QWidget として取得"""
    slider = mel.eval('$_tmp = $gPlayBackSlider')
    ptr = omui.MQtUtil.findControl(slider)
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


class BookmarkLabelOverlay(QtWidgets.QWidget):
    def __init__(self, parent, bar_ratio, font_ratio, bottom_ratio, alpha, show_range):
        super(BookmarkLabelOverlay, self).__init__(parent)
        self.setObjectName(OBJECT_NAME)

        self._bar_ratio = float(bar_ratio)
        self._font_ratio = float(font_ratio)
        self._bottom_ratio = float(bottom_ratio)
        self._alpha = max(0.0, min(1.0, float(alpha)))
        self._show_range = bool(show_range)
        self._drag = None  # (bm_node, edge)  edge = 'start' or 'stop'
        self._hover_pos = None       # 修飾キー(Ctrl/Shift)ホバー時のナビ描画用
        self._pending_rename = None  # シングルクリックrenameの遅延実行用
        self._press = None           # 中央押下情報（移動 / リネーム / 長押し判定用）

        # シングルクリック(=rename) と ダブルクリック(=範囲設定) を両立させる遅延タイマー
        self._click_timer = QtCore.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._do_pending_rename)

        # マウス操作を受ける（透過はしない）／背景は透明
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)  # ホバーでのカーソル変更/ツールチップ用
        self.setGeometry(parent.rect())

        # 親のリサイズ/移動に追従
        parent.installEventFilter(self)

        # 定期再描画（レンジのズーム・BMの増減を反映）
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(REFRESH_MS)

        self.raise_()
        self.show()

    # ----- 親ウィジェットのサイズ変更に追従 -----
    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Move):
            self.setGeometry(obj.rect())
            self.update()
        return False

    # ----- ツールチップ（自ウィジェットの ToolTip イベント） -----
    def event(self, e):
        if e.type() == QtCore.QEvent.ToolTip:
            try:
                pos = e.pos()
                gpos = e.globalPos()
            except AttributeError:
                pos = e.position().toPoint()
                gpos = e.globalPosition().toPoint()
            hit = self._hit_test(pos)
            if hit:
                bm, name, start, stop, edge, rect = hit
                QtWidgets.QToolTip.showText(gpos, self._tooltip_text(name, start, stop))
            else:
                QtWidgets.QToolTip.hideText()
            return True
        return super(BookmarkLabelOverlay, self).event(e)

    # ----- ブックマーク情報の取得（ノード名も返す） -----
    def _get_bookmarks(self):
        result = []
        for bm in (cmds.ls(type="timeSliderBookmark") or []):
            try:
                name = cmds.getAttr(bm + ".name")
                start = cmds.getAttr(bm + ".timeRangeStart")
                stop = cmds.getAttr(bm + ".timeRangeStop")
                col = cmds.getAttr(bm + ".color")[0]  # (r, g, b) 0-1
            except Exception:
                continue
            result.append((bm, name or "", start, stop, col))
        return result

    # ----- 重複を段(レーン)に振り分け -----
    def _assign_lanes(self, bookmarks):
        items = sorted(bookmarks, key=lambda b: b[2])  # startでソート
        lane_end = []   # 各レーンの現在の終了フレーム
        out = []        # (lane, bm, name, start, stop, col)
        for bm, name, start, stop, col in items:
            placed = False
            for i in range(len(lane_end)):
                if start >= lane_end[i]:   # そのレーンの最後より後なら同レーンに置ける
                    lane_end[i] = stop
                    out.append((i, bm, name, start, stop, col))
                    placed = True
                    break
            if not placed:
                lane_end.append(stop)
                out.append((len(lane_end) - 1, bm, name, start, stop, col))
        return out

    # ----- フレーム→X座標 -----
    #   Mayaのタイムスライダーは「各フレーム=1セル幅」で範囲を両端含む(inclusive)。
    #   よって分母は (max-min+1)。frame はそのフレームのセル左端を指す。
    #   帯は start のセル左端〜stop の次セル左端(=stop+1) で「フル セル」を覆う。
    def _frame_to_x(self, frame):
        min_t = cmds.playbackOptions(q=True, minTime=True)
        max_t = cmds.playbackOptions(q=True, maxTime=True)
        usable = max(self.width() - MARGIN_L - MARGIN_R, 1)
        span = (max_t - min_t) + 1.0
        return MARGIN_L + (frame - min_t) / span * usable

    # ----- X座標→フレーム（ドラッグ用の逆変換） -----
    def _x_to_frame(self, x):
        min_t = cmds.playbackOptions(q=True, minTime=True)
        max_t = cmds.playbackOptions(q=True, maxTime=True)
        usable = max(self.width() - MARGIN_L - MARGIN_R, 1)
        span = (max_t - min_t) + 1.0
        frac = (x - MARGIN_L) / float(usable)
        frac = max(0.0, min(1.0, frac))
        return min_t + frac * span

    # ----- 帯の縦位置（高さ追従） -----
    def _bar_geom(self):
        h = self.height()
        bar_h = max(int(h * self._bar_ratio), MIN_BAR_HEIGHT)
        bottom_margin = int(h * self._bottom_ratio)
        base_top = h - bar_h - bottom_margin   # レーン0(最下段)のtop
        return bar_h, base_top

    # ----- 各バーの矩形と情報を列挙（描画・ヒット判定で共用、段組み対応） -----
    def _iter_bars(self):
        bar_h, base_top = self._bar_geom()
        for lane, bm, name, start, stop, col in self._assign_lanes(self._get_bookmarks()):
            x1 = self._frame_to_x(start)
            x2 = self._frame_to_x(stop + 1)   # stop の「次セル左端」＝フルセルを覆う
            w = max(x2 - x1, 1)
            top = base_top - lane * (bar_h + LANE_GAP)  # 段が増えるほど上へ
            rect = QtCore.QRectF(x1, top, w, bar_h)
            yield rect, bm, name, start, stop, col

    # ----- 帯に描く短縮ラベル -----
    def _bar_label(self, name, start, stop):
        if self._show_range:
            rng = "({} - {})".format(int(round(start)), int(round(stop)))
            return "{} {}".format(name, rng) if name else rng
        return name

    # ----- ツールチップ用フルテキスト -----
    def _tooltip_text(self, name, start, stop):
        rng = "({} - {})".format(int(round(start)), int(round(stop)))
        return "{}  {}".format(name, rng) if name else rng

    # ----- ヒット判定：pos がどのバーの端/中央か -----
    def _hit_test(self, pos):
        px, py = pos.x(), pos.y()
        for rect, bm, name, start, stop, col in self._iter_bars():
            if rect.top() <= py <= rect.bottom():
                edge_w = min(EDGE_PX, rect.width() / 2.0)
                if rect.left() <= px <= rect.left() + edge_w:
                    return bm, name, start, stop, 'start', rect
                if rect.right() - edge_w <= px <= rect.right():
                    return bm, name, start, stop, 'stop', rect
                if rect.left() <= px <= rect.right():
                    return bm, name, start, stop, None, rect
        return None

    def _event_pos(self, event):
        try:
            return event.position().toPoint()  # PySide6
        except AttributeError:
            return event.pos()                 # PySide2

    # ----- マウス：移動（端ドラッグ=範囲変更 / 中央ドラッグ=移動 / ホバー） -----
    def mouseMoveEvent(self, event):
        pos = self._event_pos(event)
        if self._drag is not None:                 # 端ドラッグ = 範囲変更
            bm, edge = self._drag
            self._apply_drag(bm, edge, self._x_to_frame(pos.x()))
            self.update()
            event.accept()
            return
        if self._press is not None:                # 中央押下中 = 移動の可能性
            self._handle_center_move(pos)
            self.update()
            event.accept()
            return
        self._hover_pos = pos
        hit = self._hit_test(pos)
        if _DELETE_MODE:                             # デリートモード = 削除対象を赤で示す
            self.setCursor(QtCore.Qt.PointingHandCursor if hit
                           else QtCore.Qt.ArrowCursor)
            self.update()
            event.ignore()   # バー外はスクラブへ
            return
        mods = event.modifiers()
        # Ctrl / Shift を押しながらのホバーはナビUI（◀●▶ / ◁▷）を表示
        if hit and (mods & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)):
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.update()
            event.accept()
            return
        if hit and hit[4] in ('start', 'stop'):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        elif hit:
            self.setCursor(QtCore.Qt.OpenHandCursor)   # 中央=移動できることを示す
        else:
            self.unsetCursor()
        self.update()   # 端ハイライト/ナビ表示の更新・クリア用
        event.ignore()  # スクラブに流す

    # ----- 中央ドラッグによるブックマーク移動 -----
    def _handle_center_move(self, pos):
        p = self._press
        if p is None:
            return
        if not p['moving']:
            if abs(pos.x() - p['press_x']) < MOVE_THRESHOLD_PX:
                return
            # しきい値を超えた → 移動開始（rename予約は取り消す）
            p['moving'] = True
            self._cancel_pending_rename()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            try:
                cmds.undoInfo(openChunk=True)
            except Exception:
                pass
        delta = int(round(self._x_to_frame(pos.x()) - p['press_frame']))
        new_start = p['orig_start'] + delta
        new_stop = p['orig_stop'] + delta
        try:
            cmds.setAttr(p['bm'] + ".timeRangeStart", new_start)
            cmds.setAttr(p['bm'] + ".timeRangeStop", new_stop)
        except Exception as e:
            cmds.warning(str(e))

    # ----- マウス：ウィジェットから出たらホバー状態を消す -----
    def leaveEvent(self, event):
        self._hover_pos = None
        self.update()
        return super(BookmarkLabelOverlay, self).leaveEvent(event)

    # ----- マウス：押下 -----
    #   修飾なし : 端=範囲ドラッグ開始 / 中央=シングルクリックでrename(遅延)
    #   Ctrl     : ◀●▶ = 前/全体/次のブックマーク範囲を St/Ed に設定
    #   Shift    : ◁▷  = 前のStだけ / 次のEdだけを設定
    #   バー外   : タイムスライダーへ流す（スクラブ）
    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        pos = self._event_pos(event)
        hit = self._hit_test(pos)
        if not hit:
            event.ignore()   # バー外はスクラブへ
            return
        bm, name, start, stop, edge, rect = hit

        if _DELETE_MODE:
            self._delete_bookmark(bm)
            event.accept()
            return

        mods = event.modifiers()

        if mods & QtCore.Qt.ControlModifier:
            self._apply_nav_full(bm, self._zone3(pos, rect))
            event.accept()
            return
        if mods & QtCore.Qt.ShiftModifier:
            self._apply_nav_edge(bm, self._zone2(pos, rect))
            event.accept()
            return

        if edge in ('start', 'stop'):
            # 端 → 範囲ドラッグ開始
            self._cancel_pending_rename()
            self._drag = (bm, edge)
            try:
                cmds.undoInfo(openChunk=True)
            except Exception:
                pass
            event.accept()
            return

        # 中央 → 押下情報を記録。release時に「短いタップ=rename / 長押し=無視」を判定、
        #        ドラッグしたら移動（_handle_center_move）。
        self._press = {
            'bm': bm,
            'name': name,
            'rect': rect,        # rename ウィンドウをバー直上に出すため
            'press_x': pos.x(),
            'press_ms': QtCore.QDateTime.currentMSecsSinceEpoch(),
            'press_frame': self._x_to_frame(pos.x()),
            'orig_start': int(round(start)),
            'orig_stop': int(round(stop)),
            'moving': False,
        }
        event.accept()

    # ----- マウス：離す -----
    def mouseReleaseEvent(self, event):
        if self._drag is not None:                 # 端ドラッグ終了
            self._drag = None
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
            self.unsetCursor()
            self.update()
            event.accept()
            return
        if self._press is not None:                # 中央押下の後始末
            p = self._press
            self._press = None
            if p['moving']:
                # 移動確定
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception:
                    pass
                self.unsetCursor()
                self.update()
                event.accept()
                return
            # 動かしていない → 押下時間で判定
            elapsed = QtCore.QDateTime.currentMSecsSinceEpoch() - p['press_ms']
            if elapsed < LONG_PRESS_MS:
                # 短いタップ → rename（ダブルクリック判定のため遅延実行）
                self._pending_rename = (p['bm'], p['name'], p.get('rect'))
                self._click_timer.start(QtWidgets.QApplication.doubleClickInterval())
            # 長押し（elapsed >= LONG_PRESS_MS）は rename しない
            event.accept()
            return
        event.ignore()

    # ----- マウス：ダブルクリック = そのBMの範囲をタイムスライダーのSt/Edに設定 -----
    def mouseDoubleClickEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        pos = self._event_pos(event)
        hit = self._hit_test(pos)
        if not hit:
            event.ignore()
            return
        bm, name, start, stop, edge, rect = hit
        # 保留中のシングルクリックrename・押下状態を取り消す（ダブルクリック優先）
        self._cancel_pending_rename()
        self._press = None
        mods = event.modifiers()
        if mods & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
            event.accept()   # 修飾中のダブルクリックは無視
            return
        self._set_playback(start, stop)
        event.accept()

    # ----- シングルクリックrenameの遅延実行/取り消し -----
    def _do_pending_rename(self):
        if self._pending_rename is not None:
            bm, name, rect = self._pending_rename
            self._pending_rename = None
            self._rename_bookmark(bm, name, rect)
            self.update()

    def _cancel_pending_rename(self):
        self._click_timer.stop()
        self._pending_rename = None

    # ----- 範囲変更の適用 -----
    def _apply_drag(self, bm, edge, frame):
        try:
            start = int(round(cmds.getAttr(bm + ".timeRangeStart")))
            stop = int(round(cmds.getAttr(bm + ".timeRangeStop")))
        except Exception:
            return
        try:
            if edge == 'start':
                f = int(round(frame))          # 左端はセル左端基準
                f = min(f, stop - 1)           # 開始が終了を越えないように
                cmds.setAttr(bm + ".timeRangeStart", f)
            else:
                f = int(round(frame)) - 1      # 右端は stop+1 境界を掴むので -1
                f = max(f, start + 1)          # 終了が開始を下回らないように
                cmds.setAttr(bm + ".timeRangeStop", f)
        except Exception as e:
            cmds.warning(str(e))

    # ----- 名前＋色 変更ダイアログ（バー直上に表示） -----
    def _rename_bookmark(self, bm, current_name, rect=None):
        try:
            col = cmds.getAttr(bm + ".color")[0]
        except Exception:
            col = (0.5, 0.5, 0.5)
        dlg = RenameBookmarkDialog(current_name, col, parent=self)
        dlg.adjustSize()
        # バーの直上に配置
        try:
            if rect is not None:
                top_center = self.mapToGlobal(
                    QtCore.QPoint(int(rect.center().x()), int(rect.top())))
                x = int(top_center.x() - dlg.width() / 2.0)
                y = int(top_center.y() - dlg.height() - 6)
                dlg.move(x, y)
        except Exception:
            pass
        if dlg.exec_():
            new_name, rgb = dlg.result_values()
            try:
                cmds.undoInfo(openChunk=True)
            except Exception:
                pass
            try:
                cmds.setAttr(bm + ".name", new_name, type="string")
                cmds.setAttr(bm + ".color", rgb[0], rgb[1], rgb[2], type="double3")
            except Exception as e:
                cmds.warning(str(e))
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

    # ----- ブックマーク削除（デリートモード） -----
    def _delete_bookmark(self, bm):
        try:
            cmds.undoInfo(openChunk=True)
        except Exception:
            pass
        try:
            cmds.delete(bm)
        except Exception as e:
            cmds.warning(str(e))
        try:
            cmds.undoInfo(closeChunk=True)
        except Exception:
            pass
        self.update()

    # ----- ブックマークの並び順・前後・範囲 -----
    def _sorted_bookmarks(self):
        # (bm, name, start, stop, col) を start,stop 昇順で
        return sorted(self._get_bookmarks(), key=lambda b: (b[2], b[3]))

    def _neighbor(self, bm, delta):
        items = self._sorted_bookmarks()
        idx = [i for i, it in enumerate(items) if it[0] == bm]
        if not idx:
            return None
        j = idx[0] + delta
        if 0 <= j < len(items):
            return items[j]
        return None

    def _bm_range(self, bm):
        try:
            return (cmds.getAttr(bm + ".timeRangeStart"),
                    cmds.getAttr(bm + ".timeRangeStop"))
        except Exception:
            return None

    # ----- タイムスライダーの St / Ed（再生範囲）を設定 -----
    def _set_playback(self, start=None, stop=None):
        try:
            if start is not None:
                start = float(start)
                if cmds.playbackOptions(q=True, animationStartTime=True) > start:
                    cmds.playbackOptions(animationStartTime=start)
                cmds.playbackOptions(minTime=start)
            if stop is not None:
                stop = float(stop)
                if cmds.playbackOptions(q=True, animationEndTime=True) < stop:
                    cmds.playbackOptions(animationEndTime=stop)
                cmds.playbackOptions(maxTime=stop)
        except Exception as e:
            cmds.warning(str(e))

    # ----- クリックゾーン判定 -----
    def _zone3(self, pos, rect):
        # Ctrl: バーを左中右の3分割 → 'prev' / 'this' / 'next'
        fx = (pos.x() - rect.left()) / max(rect.width(), 1.0)
        if fx < 1.0 / 3.0:
            return 'prev'
        if fx < 2.0 / 3.0:
            return 'this'
        return 'next'

    def _zone2(self, pos, rect):
        # Shift: バーを左右2分割 → 'start' / 'end'
        fx = (pos.x() - rect.left()) / max(rect.width(), 1.0)
        return 'start' if fx < 0.5 else 'end'

    # ----- ナビ操作の適用 -----
    def _apply_nav_full(self, bm, zone):
        # ◀●▶ : 前 / 全ブックマーク全体 / 次 の範囲を St/Ed に設定
        if zone == 'this':
            # ● = 全ブックマークをまとめた範囲（最小Start 〜 最大End）
            items = self._sorted_bookmarks()
            if not items:
                cmds.warning(u"ブックマークがありません")
                return
            rng = (min(it[2] for it in items), max(it[3] for it in items))
        elif zone == 'prev':
            nb = self._neighbor(bm, -1)
            if nb is None:
                cmds.warning(u"前のブックマークがありません")
                return
            rng = (nb[2], nb[3])
        else:
            nb = self._neighbor(bm, +1)
            if nb is None:
                cmds.warning(u"次のブックマークがありません")
                return
            rng = (nb[2], nb[3])
        if rng:
            self._set_playback(rng[0], rng[1])

    def _apply_nav_edge(self, bm, zone):
        # ◁▷ : Stだけ=前のSt / Edだけ=次のEd
        if zone == 'start':
            nb = self._neighbor(bm, -1)
            if nb is None:
                cmds.warning(u"前のブックマークがありません")
                return
            self._set_playback(start=nb[2])
        else:
            nb = self._neighbor(bm, +1)
            if nb is None:
                cmds.warning(u"次のブックマークがありません")
                return
            self._set_playback(stop=nb[3])

    # ----- デリートモード：ホバー中のバーを赤くハイライト -----
    def _draw_delete_highlight(self, painter):
        if self._hover_pos is None:
            return
        hit = self._hit_test(self._hover_pos)
        if not hit:
            return
        rect = hit[5]
        bar_h, _ = self._bar_geom()
        br = max(4.0, min(bar_h * 0.45, 9.0))
        painter.save()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(220, 55, 55, 150))
        painter.drawRoundedRect(rect, br, br)
        # ✕ 印
        cx = rect.center().x()
        cy = rect.center().y()
        k = min(rect.height(), rect.width()) * 0.22
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        pen.setWidthF(max(1.6, bar_h * 0.10))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(cx - k, cy - k), QtCore.QPointF(cx + k, cy + k))
        painter.drawLine(QtCore.QPointF(cx - k, cy + k), QtCore.QPointF(cx + k, cy - k))
        painter.restore()

    # ----- 端ホバー/ドラッグ中のエッジを軽くハイライト（隣接バーの取り違え防止） -----
    def _draw_edge_highlight(self, painter):
        target = None  # (bm, edge)
        if self._drag is not None:
            target = self._drag
        elif self._hover_pos is not None:
            mods = QtWidgets.QApplication.queryKeyboardModifiers()
            if not (mods & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)):
                hit = self._hit_test(self._hover_pos)
                if hit and hit[4] in ('start', 'stop'):
                    target = (hit[0], hit[4])
        if target is None:
            return
        tbm, tedge = target
        for rect, bm, name, start, stop, col in self._iter_bars():
            if bm != tbm:
                continue
            ew = min(EDGE_PX + 1.0, rect.width() / 2.0)
            if tedge == 'start':
                hr = QtCore.QRectF(rect.left(), rect.top(), ew, rect.height())
            else:
                hr = QtCore.QRectF(rect.right() - ew, rect.top(), ew, rect.height())
            painter.save()
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(255, 255, 255, 115))   # 軽めのハイライト
            painter.drawRoundedRect(hr, ROUND_RADIUS, ROUND_RADIUS)
            painter.restore()
            break

    # ----- 修飾ホバー時のナビアイコン描画 -----
    def _draw_nav_icons(self, painter):
        if self._hover_pos is None:
            return
        mods = QtWidgets.QApplication.queryKeyboardModifiers()
        ctrl = bool(mods & QtCore.Qt.ControlModifier)
        shift = bool(mods & QtCore.Qt.ShiftModifier)
        if not (ctrl or shift):
            return
        hit = self._hit_test(self._hover_pos)
        if not hit:
            return
        rect = hit[5]
        painter.save()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(0, 0, 0, 150))   # 読みやすさ用の暗い下地
        painter.drawRoundedRect(rect, ROUND_RADIUS, ROUND_RADIUS)
        col = QtGui.QColor(255, 255, 255)
        cy = rect.center().y()
        if ctrl:
            gsz = min(rect.height() * 0.55, rect.width() / 3.0 * 0.7)
            self._glyph(painter, 'left',   rect.left() + rect.width() / 6.0,  cy, gsz, True, col)
            self._glyph(painter, 'circle', rect.center().x(),                 cy, gsz, True, col)
            self._glyph(painter, 'right',  rect.right() - rect.width() / 6.0, cy, gsz, True, col)
        else:  # shift
            gsz = min(rect.height() * 0.55, rect.width() / 2.0 * 0.7)
            self._glyph(painter, 'left',  rect.left() + rect.width() / 4.0,  cy, gsz, False, col)
            self._glyph(painter, 'right', rect.right() - rect.width() / 4.0, cy, gsz, False, col)
        painter.restore()

    def _glyph(self, painter, kind, cx, cy, s, filled, col):
        s = max(s, 3.0)
        painter.save()
        if filled:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(col)
        else:
            pen = QtGui.QPen(col)
            pen.setWidthF(max(1.2, s * 0.16))
            pen.setJoinStyle(QtCore.Qt.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
        if kind == 'circle':
            r = s * 0.46
            painter.setBrush(col)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(QtCore.QPointF(cx, cy), r, r)
        else:
            hw = s * 0.5
            hh = s * 0.5
            path = QtGui.QPainterPath()
            if kind == 'left':
                path.moveTo(cx + hw, cy - hh)
                path.lineTo(cx - hw, cy)
                path.lineTo(cx + hw, cy + hh)
            else:  # right
                path.moveTo(cx - hw, cy - hh)
                path.lineTo(cx + hw, cy)
                path.lineTo(cx - hw, cy + hh)
            path.closeSubpath()
            painter.drawPath(path)
        painter.restore()

    # ----- 描画 -----
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        bar_h, _ = self._bar_geom()
        # 帯の角丸（隣り合うバーの境目を分かりやすく、大きめの角丸に）
        br = max(4.0, min(bar_h * 0.45, 9.0))
        font = QtGui.QFont()
        font_px = max(int(bar_h * self._font_ratio), MIN_FONT_PX)
        font.setPixelSize(font_px)
        painter.setFont(font)
        metrics = QtGui.QFontMetrics(font)

        for rect, bm, name, start, stop, col in self._iter_bars():
            # 1) カラーバー（ブックマーク色）で塗る。角丸で境目を明確化。
            #    隣接バーと隙間を空けるため左右を僅かに詰める。
            fill = QtGui.QColor(
                int(col[0] * 255), int(col[1] * 255), int(col[2] * 255),
                int(round(self._alpha * 255))
            )
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(fill)
            bar_rect = rect.adjusted(0.75, 0.0, -0.75, 0.0)
            painter.drawRoundedRect(bar_rect, br, br)

            # 2) 帯の色の輝度から文字色を白/黒で自動選択
            lum = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
            text_color = QtGui.QColor(0, 0, 0) if lum > 0.55 else QtGui.QColor(255, 255, 255)

            # 3) ラベル（幅に収まらなければ省略。フルはツールチップで）
            if rect.width() < MIN_LABEL_W:
                continue
            label = self._bar_label(name, start, stop)
            text = metrics.elidedText(label, QtCore.Qt.ElideRight, int(rect.width()) - 4)
            if not text:
                continue
            painter.setPen(text_color)
            painter.drawText(rect, QtCore.Qt.AlignCenter, text)

        if _DELETE_MODE:
            # デリートモード：ホバー中のバーを赤くハイライト（削除対象）
            self._draw_delete_highlight(painter)
        else:
            # 端の掴み位置ハイライト（隣接バーの取り違え防止）
            self._draw_edge_highlight(painter)
            # Ctrl/Shift ホバー中のナビアイコン（◀●▶ / ◁▷）を最前面に描画
            self._draw_nav_icons(painter)

    # ----- 外部(コントロールUI)からのパラメータ反映（ライブ更新用） -----
    def set_params(self, bar_ratio=None, font_ratio=None,
                   bottom_ratio=None, alpha=None, show_range=None):
        if bar_ratio is not None:
            self._bar_ratio = float(bar_ratio)
        if font_ratio is not None:
            self._font_ratio = float(font_ratio)
        if bottom_ratio is not None:
            self._bottom_ratio = float(bottom_ratio)
        if alpha is not None:
            self._alpha = max(0.0, min(1.0, float(alpha)))
        if show_range is not None:
            self._show_range = bool(show_range)
        self.update()

    # ----- 後始末 -----
    def cleanup(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        p = self.parent()
        if p is not None:
            p.removeEventFilter(self)
        self.setParent(None)
        self.deleteLater()


def hide_overlay():
    """オーバーレイを消す"""
    global _INSTANCE
    if _INSTANCE is not None:
        try:
            _INSTANCE.cleanup()
        except Exception:
            pass
        _INSTANCE = None

    ts = _get_timeslider_widget()
    if ts is not None:
        for child in ts.findChildren(QtWidgets.QWidget, OBJECT_NAME):
            try:
                child.setParent(None)
                child.deleteLater()
            except Exception:
                pass


def show_overlay(bar_ratio=DEFAULT_BAR_RATIO,
                 font_ratio=DEFAULT_FONT_RATIO,
                 bottom_ratio=DEFAULT_BOTTOM_RATIO,
                 alpha=DEFAULT_ALPHA,
                 show_range=DEFAULT_SHOW_RANGE):
    """
    オーバーレイを表示（既存があれば作り直し）。

    bar_ratio    : タイムスライダー高さに対する1段あたりの帯の高さの割合 (0.0-1.0)
    font_ratio   : 帯の高さに対する文字サイズの割合 (0.0-1.0)
    bottom_ratio : タイムスライダー下端からの余白の割合
    alpha        : 帯の不透明度 (0.0-1.0)
    show_range   : タイムレンジ (開始 - 終了) を帯に併記するか True/False
    """
    global _INSTANCE
    hide_overlay()
    ts = _get_timeslider_widget()
    if ts is None:
        cmds.warning("タイムスライダーが取得できませんでした。")
        return None
    _INSTANCE = BookmarkLabelOverlay(ts, bar_ratio, font_ratio, bottom_ratio, alpha, show_range)
    return _INSTANCE


# =============================================================================
#  コントロールUI（タイムスライダー左隣にドッキング）
# =============================================================================
#
#  タイムスライダーの左隣に、細い縦型コントロールを横一列で並べる。
#  縦スライダーの高さ = タイムスライダーの高さ（太さ設定 1x/2x/3x/4x）に追従。
#
#   [バーOn/Off] [バーサイズ] [フォント] [アルファ] [レンジOn/Off]
#     (発光ボタン) (縦slider)  (縦slider) (縦slider)  (発光ボタン)
#
#  ■ 使い方
#      import timeslider_bookmark_labels as tsbl
#      tsbl.show_controls()   # コントロールUI表示（推奨エントリ）
#      tsbl.hide_controls()   # UI・オーバーレイをまとめて消す
# -----------------------------------------------------------------------------

PANEL_OBJECT_NAME = "bookmarkControlPanel"
WORKSPACE_CONTROL_NAME = "timeSliderBookmarkControls"   # Maya workspaceControl 名

# スライダーの内部整数レンジ（value / 100.0 が実際の比率）
BAR_RATIO_MIN, BAR_RATIO_MAX = 10, 90        # bar_ratio  0.10 - 0.90
FONT_RATIO_MIN, FONT_RATIO_MAX = 20, 100     # font_ratio 0.20 - 1.00
ALPHA_MIN, ALPHA_MAX = 0, 100                # alpha      0.00 - 1.00

PANEL_BTN_SIZE = 46                          # On/Offボタン(バー/レンジ)の一辺(px)
PANEL_PLUS_SIZE = 42                          # ＋ / − ボタン(円)の直径(px)
PANEL_SLIDER_W = 22                           # 縦スライダーの横幅(px)
PANEL_MIN_H = 96                              # パネルの最小高さ(px)

# On/Off ボタンのアイコン（ON=発光 / OFF=消灯 の2状態をベイクしたPNG, base64）
_ICON_ON_BAR    = "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"
_ICON_OFF_BAR   = "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"
_ICON_ON_RANGE  = "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"
_ICON_OFF_RANGE = "iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAAEsklEQVR4nO2asYtcVRSHvzczmQTdCAuxSGWlvcHSRjtBUAuDW1hoRMFGsJCtLDQEomCw1FWEWNqIjYWgIJbiH6CdBCwSsQga1t2dsTjv8G5mZnWdOXd+bzfngyFv3mzmnnu/c989971pdnZ2SHQM1AHc66QAMSlATAoQkwLEpAAxKUBMChCTAsSkADEpQEwKEJMCxKQAMSlATAoQkwLEpAAxKUBMChCTAsSkADEpQEwKEJMCxKQAMSlATAoQkwLEpAAxNQQ07eukUaVf0QJGwLQ9PhX83Uq8L1Osj2GEfhmwD5wGJsBe8Hcr2cMkDIDdyC+OFDAELgFPYJnyLfAZcBDYhoIh8BLwJHYJ+g74lKB+RQgYYBn/BvBqcf5C+9nHAW0ouQS8Wbx/FNgAPqDr+9KsugY0bQAPAlvtuQPsUjQFXgbOVWi3BotiOof1YYr1ybN+C+vzhBUX5ggBAJvF8bB9NcBZ4MzM/xkSEHgwnkjDmfNnsD40dP3yv98sjpcmKhMPux76TPC2hu3fPgecD2o7gvNYTAdYjD4unvmLCFkDogQclgXleR/8LeDdwLYjGGAxbdFJcI7St6WJLkMX4YHuAc8D2+1xaDm3IrtYTNtYxn/Rnq9+maydhYOijYvA28AYu96uQ/5RGWExjbEYL7bny/irNVybW8AzwDt060G5Y+4D5Q53hMW6C3xTu+HaAv4CXgFeK875tD7Vtq+uhqZ0txoausS4AjyE9eGBWo3XEuCDugG8jnWqzPgpcJPDK4x1c5P5+AZY7L7RqpIotWfAAKsqBsxXRC8Af9KPGXA/d9f4fn62IgpnHWvA7OCDTfltrJN9ELAohoY1lMrrLENn8d3wSvdSAvAYFg129eRQloITuuuuahaU7Us2hkoBfdoHyFjHICxayPaBL4Hb7WeqPUGDxXcWeJb58TgRi/DsADeYgCtYjd0H7gOeZn6DWHXwoZ4AryxuAz8ATzEvYRP4m7s3P+vG2y5vp5effQ08js2QKhVb7RkwBi4Dv2K74X26rJq07/sgwCsxr/1HwEfAdezRajVqr/xD7CH9NawzI6yDZempvCdUtj2hG/zrWMynqXwZqi2grK+vYg/pXUKfHtZ7PCMsxqvt+ZWf+f4X61iEp8W/77dtvkj/HshsAJ9jMTrVZ2eUgMMCnV14p8B72K3ecVDbEYyBT4AP2/flYnuUvi1NlIDDsrm8D3TQHu9hP+moXuL9D37DYpq9PfJvO+SQGRwl4A5dhvvLNznlLWfPmgn6e0Al5a/4ysz2n6L4XqYpXnciGl7VomfMDeB7uozxXxZ8hT0RO67cwvpQ9qnB+nqDgJuJETPAM+YylkkX2vc/YqWcutZfFt+xX8PWiMfa8z/RVUkr9ymyCvodeAt4BAvsl+Kz4zb40MX8B/bs4mFMys+RjUQK8GujB+i/gDuOg1/il1VPqAHzj1iXJlKAB+XVTZ82Wqsw+2gytF81NmInZeBnqdKvPu1G70lSgJgUICYFiEkBYlKAmBQgJgWISQFiUoCYFCAmBYhJAWJSgJgUICYFiEkBYlKAmBQgJgWISQFiUoCYFCAmBYhJAWJSgJgUICYFiEkBYlKAmH8AANjZtZe/M1gAAAAASUVORK5CYII="

_PANEL_QSS = """
QWidget#bookmarkControlPanel { background: rgba(38,38,38,210); border-radius: 6px; }
QSlider::groove:vertical { background: #232323; width: 6px; border-radius: 3px; }
QSlider::add-page:vertical { background: #232323; border-radius: 3px; }
QSlider::sub-page:vertical { background: #4aa3c7; border-radius: 3px; }
QSlider::handle:vertical {
    background: #eaeaea; height: 20px; width: 20px; margin: 0 -8px;
    border-radius: 10px; border: 1px solid #8f8f8f;
}
QSlider::handle:vertical:hover { background: #ffffff; border-color: #4aa3c7; }
QToolTip { color: #eee; background: #333; border: 1px solid #555; }
"""

COLOR_CONTROL_NAME = "timeSliderBookmarkColors"        # カラータブ用 workspaceControl 名

_PANEL = None                                # コントロールUIの二重起動防止用
_WIN = None                                  # メイン(バーコントロール)ウィンドウ
_WIN_COLOR = None                            # カラーウィンドウ
_WS_PARAMS = {"bottom_ratio": DEFAULT_BOTTOM_RATIO}   # workspaceControl uiScript 用パラメータ

# 旧 MayaQWidgetDockableMixin 版が作る workspaceControl 名（後方互換で掃除に使用）
_WS_MIXIN_CONTROL = WORKSPACE_CONTROL_NAME + "WorkspaceControl"
_COLOR_MIXIN_CONTROL = COLOR_CONTROL_NAME + "WorkspaceControl"


def _module_dir():
    """このモジュール(.py)が置かれているフォルダの絶対パス。取得不能なら空文字。"""
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return ""


def _module_name():
    """import 名（ファイル名の拡張子抜き）。__main__ 実行やリネームにも耐える。"""
    try:
        nm = os.path.splitext(os.path.basename(__file__))[0]
        if nm and nm != "__init__":
            return nm
    except Exception:
        pass
    return __name__


def _uiscript(kind):
    """workspaceControl の uiScript 文字列を組み立てる。

    Maya 再起動時の自動復元でも実行されるため、起動時スクリプトパスに
    モジュールが無くても import できるよう、モジュールの絶対パスを焼き込む。
    """
    d = _module_dir().replace("\\", "/")
    mod = _module_name()
    fn = "_ws_ui_control" if kind == "control" else "_ws_ui_color"
    lines = []
    if d:
        lines.append("import sys")
        lines.append("_d = r'%s'" % d)
        lines.append("if _d not in sys.path: sys.path.insert(0, _d)")
    lines.append("import %s as _t" % mod)
    lines.append("_t.%s()" % fn)
    return "\n".join(lines)


def _ws_ui_control():
    """workspaceControl(バーコントロール) の uiScript から呼ばれる。"""
    _restore_ws("control")


def _ws_ui_color():
    """workspaceControl(カラー) の uiScript から呼ばれる。"""
    _restore_ws("color")


def _pixmap_from_b64(data):
    pm = QtGui.QPixmap()
    try:
        pm.loadFromData(base64.b64decode(data), "PNG")
    except Exception:
        pass
    return pm


# --- ブックマーク追加 --------------------------------------------------------

# 追加時に順番に割り当てる色（見やすい7色）
_BM_PALETTE = [
    (0.90, 0.32, 0.32), (0.95, 0.62, 0.22), (0.92, 0.86, 0.28),
    (0.42, 0.80, 0.42), (0.30, 0.72, 0.92), (0.55, 0.50, 0.92),
    (0.92, 0.46, 0.82),
]


def _hue_far_random(prev_hue, min_sep=0.13):
    """prev_hue から色相が min_sep 以上離れたランダム hue を返す。"""
    for _ in range(30):
        h = random.random()
        if prev_hue is None:
            return h
        d = abs(h - prev_hue)
        if min(d, 1.0 - d) >= min_sep:
            return h
    return (prev_hue + 0.5) % 1.0 if prev_hue is not None else random.random()


def _random_color(prev_hue=None):
    """見やすいランダム色 (r,g,b 0-1) と使用した hue を返す。"""
    h = _hue_far_random(prev_hue)
    s = random.uniform(0.55, 0.9)
    v = random.uniform(0.78, 0.98)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (r, g, b), h


def randomize_colors():
    """全ブックマークの色をランダムに再設定する（時間順で隣り合う色は別色）。"""
    bms = cmds.ls(type="timeSliderBookmark") or []
    if not bms:
        cmds.warning(u"ブックマークがありません")
        return

    def _start(b):
        try:
            return cmds.getAttr(b + ".timeRangeStart")
        except Exception:
            return 0.0
    bms = sorted(bms, key=_start)

    try:
        cmds.undoInfo(openChunk=True)
    except Exception:
        pass
    prev_h = None
    for b in bms:
        rgb, prev_h = _random_color(prev_h)
        try:
            cmds.setAttr(b + ".color", rgb[0], rgb[1], rgb[2], type="double3")
        except Exception:
            pass
    try:
        cmds.undoInfo(closeChunk=True)
    except Exception:
        pass
    if _INSTANCE is not None:
        _INSTANCE.update()


def _playback_slider():
    return mel.eval('$_tmp = $gPlayBackSlider')


def _current_range():
    """タイムスライダーの選択範囲（無ければ再生範囲 min/max）を返す。"""
    try:
        r = cmds.timeControl(_playback_slider(), q=True, rangeArray=True)
        if r and (r[1] - r[0]) > 1:      # 実際に範囲選択されている
            return float(r[0]), float(r[1])
    except Exception:
        pass
    mn = cmds.playbackOptions(q=True, minTime=True)
    mx = cmds.playbackOptions(q=True, maxTime=True)
    return float(mn), float(mx)


def add_bookmark(name=None, start=None, stop=None, color=None):
    """現在の範囲に Time Slider Bookmark を追加する。"""
    try:
        cmds.loadPlugin('timeSliderBookmark', quiet=True)
    except Exception:
        pass

    if start is None or stop is None:
        s, e = _current_range()
        start = s if start is None else start
        stop = e if stop is None else stop
    start, stop = float(start), float(stop)
    if start > stop:
        start, stop = stop, start

    n = len(cmds.ls(type="timeSliderBookmark") or [])
    if color is None:
        color = _BM_PALETTE[n % len(_BM_PALETTE)]
    if not name:
        name = u"BM_%02d" % (n + 1)

    # 1) 公式ヘルパ（あれば最優先。ネイティブの色帯にも正しく載る）
    try:
        from maya.plugin.timeSliderBookmark.timeSliderBookmark import createBookmark
        return createBookmark(name=name, start=start, stop=stop, color=color)
    except Exception:
        pass

    # 2) フォールバック：ノードを直接作成
    try:
        bm = cmds.createNode("timeSliderBookmark")
        cmds.setAttr(bm + ".name", name, type="string")
        cmds.setAttr(bm + ".timeRangeStart", start)
        cmds.setAttr(bm + ".timeRangeStop", stop)
        cmds.setAttr(bm + ".color", color[0], color[1], color[2], type="double3")
        return bm
    except Exception as e:
        cmds.warning(u"ブックマーク作成に失敗しました: %s" % e)
        return None


class PlusButton(QtWidgets.QAbstractButton):
    """ラベル無しの「＋」ボタン（ブックマーク追加用）。"""

    def __init__(self, tip="", parent=None):
        super(PlusButton, self).__init__(parent)
        self._hover = False
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        if tip:
            self.setToolTip(tip)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = self.rect()
        d = min(r.width(), r.height()) - 4
        cx, cy = r.center().x() + 0.5, r.center().y() + 0.5
        circle = QtCore.QRectF(cx - d / 2.0, cy - d / 2.0, d, d)
        # 円形の背景（ホバーでアクセント色に）
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(74, 163, 199, 240) if self._hover
                   else QtGui.QColor(82, 82, 82, 210))
        p.drawEllipse(circle)
        # ＋
        L = d * 0.27
        pen = QtGui.QPen(QtGui.QColor(245, 245, 245))
        pen.setWidthF(max(3.0, d * 0.11))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(cx - L, cy), QtCore.QPointF(cx + L, cy))
        p.drawLine(QtCore.QPointF(cx, cy - L), QtCore.QPointF(cx, cy + L))


class MinusToggleButton(QtWidgets.QAbstractButton):
    """円形の「−」トグルボタン。ON(デリートモード)=赤く発光 / OFF=グレー。"""

    def __init__(self, tip="", parent=None):
        super(MinusToggleButton, self).__init__(parent)
        self._hover = False
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        if tip:
            self.setToolTip(tip)
        self.toggled.connect(lambda *_: self.update())

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = self.rect()
        d = min(r.width(), r.height()) - 4
        cx, cy = r.center().x() + 0.5, r.center().y() + 0.5
        on = self.isChecked()
        if on:
            # 発光ハロー（赤）
            p.setPen(QtCore.Qt.NoPen)
            for k, a in ((1.5, 45), (1.28, 70)):
                dd = d * k
                p.setBrush(QtGui.QColor(230, 70, 70, a))
                p.drawEllipse(QtCore.QRectF(cx - dd / 2.0, cy - dd / 2.0, dd, dd))
        circle = QtCore.QRectF(cx - d / 2.0, cy - d / 2.0, d, d)
        p.setPen(QtCore.Qt.NoPen)
        if on:
            p.setBrush(QtGui.QColor(226, 74, 74) if self._hover
                       else QtGui.QColor(210, 62, 62))
        else:
            p.setBrush(QtGui.QColor(92, 92, 92, 220) if self._hover
                       else QtGui.QColor(78, 78, 78, 200))
        p.drawEllipse(circle)
        # −
        L = d * 0.27
        pen = QtGui.QPen(QtGui.QColor(245, 245, 245))
        pen.setWidthF(max(3.0, d * 0.11))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(cx - L, cy), QtCore.QPointF(cx + L, cy))


class IconToggleButton(QtWidgets.QAbstractButton):
    """ラベル無しのトグルボタン。ON時は発光アイコン、OFF時は消灯アイコンを表示する。"""

    def __init__(self, on_pix, off_pix, tip="", parent=None):
        super(IconToggleButton, self).__init__(parent)
        self._on = on_pix
        self._off = off_pix
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        if tip:
            self.setToolTip(tip)
        self.toggled.connect(lambda *_: self.update())

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        pix = self._on if self.isChecked() else self._off
        if pix.isNull():
            return
        r = self.rect()
        side = min(r.width(), r.height())
        target = max(8, int(side * 1.0))       # ボタン一杯まで大きく表示
        sp = pix.scaled(target, target, QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation)
        x = int(r.center().x() - sp.width() / 2.0)
        y = int(r.center().y() - sp.height() / 2.0)
        p.drawPixmap(x, y, sp)


class RangeVSlider(QtWidgets.QWidget):
    """縦型の2ハンドル レンジスライダー。
    下つまみ=バーの下端位置、上つまみ=バーの上端位置。値は 0..100（下端0/上端100）。
    valueChanged を発火する。"""
    valueChanged = QtCore.Signal()

    def __init__(self, lo, hi, parent=None):
        super(RangeVSlider, self).__init__(parent)
        self._min = 0.0
        self._max = 100.0
        self._gap = 3.0                      # 上下つまみの最小間隔
        self._hr = 9.0                       # ハンドル半径(px)
        self._lo = max(self._min, float(lo))
        self._hi = min(self._max, float(hi))
        self._drag = None                    # 'lo' | 'hi'
        self.setFixedWidth(PANEL_SLIDER_W)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                           QtWidgets.QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def values(self):
        return self._lo, self._hi

    def setValues(self, lo, hi):
        self._lo = max(self._min, min(float(lo), self._max))
        self._hi = max(self._min, min(float(hi), self._max))
        if self._hi < self._lo + self._gap:
            self._hi = min(self._max, self._lo + self._gap)
        self.update()
        self.valueChanged.emit()

    def _yspan(self):
        r = self.rect()
        return r.top() + self._hr, r.bottom() - self._hr   # (y_top, y_bottom)

    def _v2y(self, v):
        yt, yb = self._yspan()
        frac = (v - self._min) / (self._max - self._min)
        return yb - frac * (yb - yt)         # min→下端(yb), max→上端(yt)

    def _y2v(self, y):
        yt, yb = self._yspan()
        frac = (yb - y) / float(max(yb - yt, 1))
        frac = max(0.0, min(1.0, frac))
        return self._min + frac * (self._max - self._min)

    def _epos(self, event):
        try:
            return event.position().toPoint()
        except AttributeError:
            return event.pos()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        cx = self.rect().center().x()
        yt, yb = self._yspan()
        p.setPen(QtCore.Qt.NoPen)
        # groove
        p.setBrush(QtGui.QColor(35, 35, 35))
        p.drawRoundedRect(QtCore.QRectF(cx - 3, yt, 6, yb - yt), 3, 3)
        ylo = self._v2y(self._lo)
        yhi = self._v2y(self._hi)
        # 上つまみ(yhi)〜下つまみ(ylo) の間を塗る＝バーが占める帯
        p.setBrush(QtGui.QColor(74, 163, 199))
        p.drawRoundedRect(QtCore.QRectF(cx - 3, yhi, 6, ylo - yhi), 3, 3)
        # handles
        for y in (ylo, yhi):
            pen = QtGui.QPen(QtGui.QColor(143, 143, 143))
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setBrush(QtGui.QColor(234, 234, 234))
            p.drawEllipse(QtCore.QPointF(cx, y), self._hr, self._hr)

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        y = self._epos(event).y()
        dlo = abs(y - self._v2y(self._lo))
        dhi = abs(y - self._v2y(self._hi))
        self._drag = 'lo' if dlo <= dhi else 'hi'
        self._apply_drag(y)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self._apply_drag(self._epos(event).y())
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag = None
        event.accept()

    def _apply_drag(self, y):
        v = self._y2v(y)
        if self._drag == 'lo':
            self._lo = max(self._min, min(v, self._hi - self._gap))
        else:
            self._hi = min(self._max, max(v, self._lo + self._gap))
        self.update()
        self.valueChanged.emit()


_ADD_DIALOG_QSS = """
QFrame#addFrame { background: #3a3a3a; border: 1px solid #565656; border-radius: 8px; }
QLabel#fieldLbl { color: #9fb7c2; }
QLineEdit, QSpinBox {
    background: #2b2b2b; color: #eee; border: 1px solid #555;
    border-radius: 4px; padding: 3px 5px;
}
QLineEdit:focus, QSpinBox:focus { border: 1px solid #4aa3c7; }
QToolTip { color: #eee; background: #333; border: 1px solid #555; }
"""


class ColorSwatch(QtWidgets.QAbstractButton):
    """クリックで色を選ぶ小さなカラースウォッチ（Maya標準のブックマークマネージャ風）。"""

    def __init__(self, rgb, parent=None):
        super(ColorSwatch, self).__init__(parent)
        self._rgb = tuple(rgb)
        self.setFixedSize(30, 26)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setToolTip(u"色を選択")
        self.clicked.connect(self._pick)

    def color(self):
        return self._rgb

    def setColor(self, rgb):
        self._rgb = tuple(rgb)
        self.update()

    def _pick(self):
        c = QtGui.QColor.fromRgbF(self._rgb[0], self._rgb[1], self._rgb[2])
        picked = QtWidgets.QColorDialog.getColor(c, self, u"ブックマークの色")
        if picked.isValid():
            self.setColor((picked.redF(), picked.greenF(), picked.blueF()))

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        col = QtGui.QColor.fromRgbF(self._rgb[0], self._rgb[1], self._rgb[2])
        pen = QtGui.QPen(QtGui.QColor(120, 120, 120))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(col)
        p.drawRoundedRect(r, 4, 4)


class DialogIconButton(QtWidgets.QAbstractButton):
    """円形アイコンボタン。kind: 'cancel'(✕) / 'add'(しおり＋) / 'apply'(✓)。"""

    def __init__(self, kind, tip="", parent=None):
        super(DialogIconButton, self).__init__(parent)
        self._kind = kind
        self._hover = False
        self.setFixedSize(40, 40)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        if tip:
            self.setToolTip(tip)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = self.rect()
        d = min(r.width(), r.height()) - 6
        cx, cy = r.center().x() + 0.5, r.center().y() + 0.5
        circle = QtCore.QRectF(cx - d / 2.0, cy - d / 2.0, d, d)
        p.setPen(QtCore.Qt.NoPen)
        if self._kind in ('add', 'apply'):
            p.setBrush(QtGui.QColor(74, 163, 199) if self._hover
                       else QtGui.QColor(60, 120, 145))
        else:
            p.setBrush(QtGui.QColor(150, 80, 80) if self._hover
                       else QtGui.QColor(78, 78, 78))
        p.drawEllipse(circle)

        white = QtGui.QColor(242, 242, 242)
        if self._kind == 'cancel':
            pen = QtGui.QPen(white)
            pen.setWidthF(max(2.4, d * 0.09))
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            k = d * 0.20
            p.drawLine(QtCore.QPointF(cx - k, cy - k), QtCore.QPointF(cx + k, cy + k))
            p.drawLine(QtCore.QPointF(cx - k, cy + k), QtCore.QPointF(cx + k, cy - k))
        elif self._kind == 'apply':
            pen = QtGui.QPen(white)
            pen.setWidthF(max(2.6, d * 0.10))
            pen.setCapStyle(QtCore.Qt.RoundCap)
            pen.setJoinStyle(QtCore.Qt.RoundJoin)
            p.setPen(pen)
            path = QtGui.QPainterPath()
            path.moveTo(cx - d * 0.22, cy + d * 0.02)
            path.lineTo(cx - d * 0.05, cy + d * 0.18)
            path.lineTo(cx + d * 0.24, cy - d * 0.18)
            p.drawPath(path)
        else:
            self._draw_bookmark_plus(p, cx, cy, d, white)

    def _draw_bookmark_plus(self, p, cx, cy, d, col):
        # しおり(ブックマーク)の輪郭 ＋ 上部にプラス
        w = d * 0.44
        h = d * 0.54
        notch = h * 0.22
        x0 = cx - w / 2.0
        x1 = cx + w / 2.0
        y0 = cy - h / 2.0
        y1 = cy + h / 2.0
        path = QtGui.QPainterPath()
        path.moveTo(x0, y0)
        path.lineTo(x1, y0)
        path.lineTo(x1, y1)
        path.lineTo(cx, y1 - notch)
        path.lineTo(x0, y1)
        path.closeSubpath()
        pen = QtGui.QPen(col)
        pen.setWidthF(max(1.8, d * 0.065))
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)
        # plus
        pcx = cx
        pcy = y0 + h * 0.36
        L = d * 0.10
        pen2 = QtGui.QPen(col)
        pen2.setWidthF(max(1.8, d * 0.07))
        pen2.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen2)
        p.drawLine(QtCore.QPointF(pcx - L, pcy), QtCore.QPointF(pcx + L, pcy))
        p.drawLine(QtCore.QPointF(pcx, pcy - L), QtCore.QPointF(pcx, pcy + L))


def _fill_dialog_grid(grid, cols, buttons):
    """ダイアログ用グリッド: row0=ラベル(下寄せ), row1=コントロール(縦中央)。
    ボタンもrow1に縦中央で並べ、コントロール行を中央でそろえる。"""
    lblflags = QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom
    ctlflags = QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft
    for i, (label, w) in enumerate(cols):
        lbl = QtWidgets.QLabel(label)
        lbl.setObjectName("fieldLbl")
        grid.addWidget(lbl, 0, i, lblflags)
        grid.addWidget(w, 1, i, ctlflags)
    for j, b in enumerate(buttons):
        grid.addWidget(b, 1, len(cols) + j,
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignHCenter)


class AddBookmarkDialog(QtWidgets.QDialog):
    """タイトルバー無し・横並びのコンパクトなブックマーク追加ポップアップ。
    Name / Start / End を横並びに、✕(キャンセル) と ◯(追加) のアイコンボタン。"""

    def __init__(self, parent=None):
        super(AddBookmarkDialog, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
                            | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(_ADD_DIALOG_QSS)

        s, e = _current_range()
        n = len(cmds.ls(type="timeSliderBookmark") or []) + 1

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QtWidgets.QFrame()
        frame.setObjectName("addFrame")
        outer.addWidget(frame)

        grid = QtWidgets.QGridLayout(frame)
        grid.setContentsMargins(12, 6, 12, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(1)          # ラベルとコントロールの距離を詰める

        default_rgb = _BM_PALETTE[(n - 1) % len(_BM_PALETTE)]
        self.colorSwatch = ColorSwatch(default_rgb)
        self.nameEdit = QtWidgets.QLineEdit(u"BM_%02d" % n)
        self.nameEdit.setFixedWidth(96)
        self.startSpin = QtWidgets.QSpinBox()
        self.startSpin.setRange(-1000000, 1000000)
        self.startSpin.setValue(int(round(s)))
        self.startSpin.setFixedWidth(66)
        self.endSpin = QtWidgets.QSpinBox()
        self.endSpin.setRange(-1000000, 1000000)
        self.endSpin.setValue(int(round(e)))
        self.endSpin.setFixedWidth(66)
        self.cancelBtn = DialogIconButton('cancel', tip=u"キャンセル")
        self.addBtn = DialogIconButton('add', tip=u"ブックマークを追加")

        _fill_dialog_grid(
            grid,
            [(u"Color", self.colorSwatch), (u"Name", self.nameEdit),
             (u"Start", self.startSpin), (u"End", self.endSpin)],
            [self.cancelBtn, self.addBtn])

        self.addBtn.clicked.connect(self._do)
        self.cancelBtn.clicked.connect(self.reject)
        self.nameEdit.returnPressed.connect(self._do)
        self.nameEdit.setFocus()
        self.nameEdit.selectAll()

    def _do(self):
        name = self.nameEdit.text().strip()
        start = self.startSpin.value()
        stop = self.endSpin.value()
        add_bookmark(name=name or None, start=start, stop=stop,
                     color=self.colorSwatch.color())
        if _INSTANCE is not None:
            _INSTANCE.update()
        self.accept()


class RenameBookmarkDialog(QtWidgets.QDialog):
    """名前変更＋色変更のコンパクトなポップアップ（追加ダイアログと同デザイン）。"""

    def __init__(self, current_name, rgb, parent=None):
        super(RenameBookmarkDialog, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
                            | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(_ADD_DIALOG_QSS)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QtWidgets.QFrame()
        frame.setObjectName("addFrame")
        outer.addWidget(frame)
        grid = QtWidgets.QGridLayout(frame)
        grid.setContentsMargins(12, 6, 12, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(1)

        self.colorSwatch = ColorSwatch(rgb)
        self.nameEdit = QtWidgets.QLineEdit(current_name)
        self.nameEdit.setFixedWidth(120)
        self.cancelBtn = DialogIconButton('cancel', tip=u"キャンセル")
        self.applyBtn = DialogIconButton('apply', tip=u"適用")

        _fill_dialog_grid(
            grid,
            [(u"Color", self.colorSwatch), (u"Name", self.nameEdit)],
            [self.cancelBtn, self.applyBtn])

        self.applyBtn.clicked.connect(self.accept)
        self.cancelBtn.clicked.connect(self.reject)
        self.nameEdit.returnPressed.connect(self.accept)
        self.nameEdit.setFocus()
        self.nameEdit.selectAll()

    def result_values(self):
        return self.nameEdit.text().strip(), self.colorSwatch.color()


class RainbowBookmarkButton(QtWidgets.QAbstractButton):
    """虹色のブックマークアイコンボタン（全色ランダム再設定用）。"""

    def __init__(self, tip="", parent=None):
        super(RainbowBookmarkButton, self).__init__(parent)
        self._hover = False
        self.setFixedSize(56, 56)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        if tip:
            self.setToolTip(tip)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = self.rect()
        d = (min(r.width(), r.height()) - 8) * (1.06 if self._hover else 1.0)
        cx, cy = r.center().x() + 0.5, r.center().y() + 0.5
        w = d * 0.62
        h = d * 0.86
        notch = h * 0.20
        x0 = cx - w / 2.0
        x1 = cx + w / 2.0
        y0 = cy - h / 2.0
        y1 = cy + h / 2.0
        path = QtGui.QPainterPath()
        path.moveTo(x0, y0)
        path.lineTo(x1, y0)
        path.lineTo(x1, y1)
        path.lineTo(cx, y1 - notch)
        path.lineTo(x0, y1)
        path.closeSubpath()
        # 虹色グラデーション（縦方向）
        grad = QtGui.QLinearGradient(x0, y0, x0, y1)
        stops = 7
        for i in range(stops + 1):
            t = i / float(stops)
            rr, gg, bb = colorsys.hsv_to_rgb(t, 0.85, 1.0)
            grad.setColorAt(t, QtGui.QColor.fromRgbF(rr, gg, bb))
        p.setBrush(QtGui.QBrush(grad))
        pen = QtGui.QPen(QtGui.QColor(245, 245, 245))
        pen.setWidthF(max(1.6, d * 0.05))
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)


class ColorTab(QtWidgets.QWidget):
    """カラータブ：虹色ブックマークボタンで全色ランダム再設定。"""

    def __init__(self, parent=None):
        super(ColorTab, self).__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setObjectName("bmColorTab")
        self.setStyleSheet("QWidget#bmColorTab { background: rgba(38,38,38,210); }")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.addStretch(1)
        self.randomBtn = RainbowBookmarkButton(
            tip=u"全ブックマークの色をランダムに再設定（隣り合う色は別色）")
        self.randomBtn.clicked.connect(lambda: randomize_colors())
        lay.addWidget(self.randomBtn)
        lay.addStretch(1)


class DragGrip(QtWidgets.QWidget):
    """パネル左端のドラッグ用グリップ。
    ドラッグ=移動（独立フロート）／ダブルクリック=タイムスライダー横に再ドック。"""

    def __init__(self, panel):
        super(DragGrip, self).__init__(panel)
        self._panel = panel
        self._off = None
        self.setFixedWidth(14)
        self.setCursor(QtCore.Qt.OpenHandCursor)
        self.setToolTip(u"ドラッグ=移動（独立）／タイムスライダー横に近づけて離すと自動ドック／"
                        u"ダブルクリックでも再ドック")

    def _gpos(self, event):
        try:
            return event.globalPosition().toPoint()
        except AttributeError:
            return event.globalPos()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(160, 160, 160, 180))
        cx = self.rect().center().x()
        cy = self.rect().center().y()
        for dy in (-8, -4, 0, 4, 8):
            for dx in (-2.0, 2.0):
                p.drawEllipse(QtCore.QPointF(cx + dx, cy + dy), 1.1, 1.1)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._panel._dock_mode == "floating":
            self._off = self._gpos(event) - self._panel.pos()
            self._panel.set_docked(False)   # ドラッグ開始で独立モードへ
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._off is not None:
            self._panel.move(self._gpos(event) - self._off)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._off = None
        # ドッキング位置の近くで離したら自動再ドック
        try:
            geo = self._panel._docked_geometry()
            if geo is not None:
                tx, ty, _, _ = geo
                pp = self._panel.pos()
                if abs(pp.x() - tx) <= DOCK_SNAP_PX and abs(pp.y() - ty) <= DOCK_SNAP_PX:
                    self._panel.set_docked(True)
        except Exception:
            pass
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self._panel.set_docked(True)        # 再ドック（タイムスライダー横へスナップ）
        event.accept()


class BookmarkControlPanel(QtWidgets.QWidget):
    """タイムスライダー横にドッキング／独立フロート可能なコントロールパネル。"""

    def __init__(self, timeslider, bottom_ratio=DEFAULT_BOTTOM_RATIO,
                 force_floating=False, mode="floating", parent=None):
        super(BookmarkControlPanel, self).__init__(parent)
        self.setObjectName(PANEL_OBJECT_NAME)
        self._timeslider = timeslider
        self._dock_mode = None
        self._mode = mode            # "workspace"=Maya標準ドック / "floating"=タイムスライダー横
        self._bottom_ratio = float(bottom_ratio)   # UIには出さず、起動引数で指定
        self._force_floating = bool(force_floating)
        self._pos_timer = None
        self._docked = True          # True=タイムスライダー横に追従 / False=独立フロート
        self._add_dialog = None
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet(_PANEL_QSS)
        self.setMinimumHeight(PANEL_MIN_H)

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.grip = None
        if self._mode == "floating":
            self.grip = DragGrip(self)
            self.grip.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                    QtWidgets.QSizePolicy.Expanding)
        self.addBtn = PlusButton(tip=u"ブックマーク追加（Name/Start/End を入力）")
        self.minusBtn = MinusToggleButton(
            tip=u"デリートモード（ONの間、バーを左クリックで削除）")
        self.barBtn = IconToggleButton(
            _pixmap_from_b64(_ICON_ON_BAR), _pixmap_from_b64(_ICON_OFF_BAR),
            tip=u"バー表示 ON/OFF")
        self.rangeBtn = IconToggleButton(
            _pixmap_from_b64(_ICON_ON_RANGE), _pixmap_from_b64(_ICON_OFF_RANGE),
            tip=u"レンジ表示 ON/OFF")
        # On/Offボタンは固定サイズで縦センター（縦長にならないように）
        for b in (self.barBtn, self.rangeBtn):
            b.setFixedSize(PANEL_BTN_SIZE, PANEL_BTN_SIZE)
        self.addBtn.setFixedSize(PANEL_PLUS_SIZE, PANEL_PLUS_SIZE)     # ＋は円
        self.minusBtn.setFixedSize(PANEL_PLUS_SIZE, PANEL_PLUS_SIZE)   # −も円

        # 保存された設定（optionVar）を復元。無ければ既定値。
        _lo0 = float(_ov_get('bar_lo', self._bottom_ratio * 100.0))
        _hi0 = float(_ov_get('bar_hi', min(100.0, _lo0 + DEFAULT_BAR_RATIO * 100.0)))
        _font0 = int(_ov_get('font', int(round(DEFAULT_FONT_RATIO * 100))))
        _alpha0 = int(_ov_get('alpha', int(round(DEFAULT_ALPHA * 100))))
        _range0 = bool(_ov_get('show_range', 1))
        _baron0 = bool(_ov_get('bar_on', 1))

        # バーサイズは2ハンドル：下つまみ=バー下端(bottom_ratio)、上つまみ=バー上端
        self.barSlider = RangeVSlider(_lo0, _hi0)
        self.barSlider.setToolTip(u"バーの下端(下つまみ)と上端(上つまみ)を調整")
        self.fontSlider = self._make_slider(
            FONT_RATIO_MIN, FONT_RATIO_MAX, _font0, u"フォントサイズ")
        self.alphaSlider = self._make_slider(
            ALPHA_MIN, ALPHA_MAX, _alpha0, u"アルファ")

        vc = QtCore.Qt.AlignVCenter
        if self.grip is not None:
            lay.addWidget(self.grip)      # 左端＝ドラッグ用グリップ（floating時のみ）
        lay.addWidget(self.barBtn, 0, vc)
        lay.addWidget(self.barSlider)
        lay.addWidget(self.fontSlider)
        lay.addWidget(self.alphaSlider)
        lay.addWidget(self.rangeBtn, 0, vc)
        # 右端＝＋（上）／−デリートモード（下）を縦に積む
        addcol = QtWidgets.QVBoxLayout()
        addcol.setContentsMargins(0, 0, 0, 0)
        addcol.setSpacing(4)
        addcol.addStretch(1)
        addcol.addWidget(self.addBtn, 0, QtCore.Qt.AlignHCenter)
        addcol.addWidget(self.minusBtn, 0, QtCore.Qt.AlignHCenter)
        addcol.addStretch(1)
        lay.addLayout(addcol)

        # 保存状態を反映（シグナル接続前に設定して誤発火を防ぐ）
        self.barBtn.setChecked(_baron0)
        self.rangeBtn.setChecked(_range0)

        self.addBtn.clicked.connect(self._on_add)
        self.minusBtn.toggled.connect(self._on_delete_toggled)
        self.barBtn.toggled.connect(self._on_bar_toggled)
        self.rangeBtn.toggled.connect(self._on_range_toggled)
        self.barSlider.valueChanged.connect(self._on_bar_range_changed)
        for s in (self.fontSlider, self.alphaSlider):
            s.valueChanged.connect(self._on_slider_changed)

        if self._mode == "floating":
            self._dock_to_timeslider()
        if self.barBtn.isChecked():
            self._apply_show()  # 初期オーバーレイ表示（バーON時のみ）

    # ----- スライダー生成 -----
    def _make_slider(self, lo, hi, val, tip):
        s = QtWidgets.QSlider(QtCore.Qt.Vertical, self)
        s.setMinimum(lo)
        s.setMaximum(hi)
        s.setValue(val)
        s.setFixedWidth(PANEL_SLIDER_W)
        s.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                        QtWidgets.QSizePolicy.Expanding)
        s.setFocusPolicy(QtCore.Qt.NoFocus)
        s.setToolTip(tip)
        return s

    # ----- スライダー現在値→比率 -----
    def _cur_bar_bottom(self):
        # バーサイズ2ハンドル → (bar_ratio, bottom_ratio)
        lo, hi = self.barSlider.values()
        return (hi - lo) / 100.0, lo / 100.0

    def _cur_font_ratio(self):
        return self.fontSlider.value() / 100.0

    def _cur_alpha(self):
        return self.alphaSlider.value() / 100.0

    # ----- オーバーレイ操作 -----
    def _apply_show(self):
        bar_ratio, bottom_ratio = self._cur_bar_bottom()
        show_overlay(bar_ratio=bar_ratio,
                     font_ratio=self._cur_font_ratio(),
                     bottom_ratio=bottom_ratio,
                     alpha=self._cur_alpha(),
                     show_range=self.rangeBtn.isChecked())

    # ----- 設定の保存（optionVar） -----
    def _save(self):
        try:
            lo, hi = self.barSlider.values()
            _ov_set('bar_lo', float(lo))
            _ov_set('bar_hi', float(hi))
            _ov_set('font', int(self.fontSlider.value()))
            _ov_set('alpha', int(self.alphaSlider.value()))
            _ov_set('bar_on', bool(self.barBtn.isChecked()))
            _ov_set('show_range', bool(self.rangeBtn.isChecked()))
        except Exception:
            pass

    def _on_bar_toggled(self, on):
        if on:
            self._apply_show()
        else:
            hide_overlay()
        self._save()

    def _on_range_toggled(self, on):
        if _INSTANCE is not None:
            _INSTANCE.set_params(show_range=on)
        self._save()

    def _on_delete_toggled(self, on):
        # デリートモードON/OFF（保存はしない＝毎起動OFF）
        if on and not self.barBtn.isChecked():
            # バー非表示だと削除対象が見えないので自動でバーON
            self.barBtn.setChecked(True)
        _set_delete_mode(on)

    def _on_bar_range_changed(self):
        if self.barBtn.isChecked() and _INSTANCE is not None:
            bar_ratio, bottom_ratio = self._cur_bar_bottom()
            _INSTANCE.set_params(bar_ratio=bar_ratio, bottom_ratio=bottom_ratio)
        self._save()

    def _on_slider_changed(self, *_):
        if self.barBtn.isChecked() and _INSTANCE is not None:
            _INSTANCE.set_params(font_ratio=self._cur_font_ratio(),
                                 alpha=self._cur_alpha())
        self._save()

    def _on_add(self):
        # コンパクトな追加ウィンドウ（Name/Start/End ＋ 追加）を＋ボタンの直上に開く
        dlg = AddBookmarkDialog(self)
        self._add_dialog = dlg
        dlg.adjustSize()
        try:
            top_center = self.addBtn.mapToGlobal(
                QtCore.QPoint(self.addBtn.width() // 2, 0))
            x = int(top_center.x() - dlg.width() / 2.0)
            y = int(top_center.y() - dlg.height() - 6)
            dlg.move(x, y)
        except Exception:
            pass
        dlg.show()
        dlg.raise_()

    # ----- タイムスライダー左隣へドッキング -----
    def _dock_to_timeslider(self):
        ts = self._timeslider
        parent = ts.parentWidget() if ts is not None else None
        lay = parent.layout() if parent is not None else None
        horizontal = (isinstance(lay, QtWidgets.QBoxLayout) and
                      lay.direction() in (QtWidgets.QBoxLayout.LeftToRight,
                                          QtWidgets.QBoxLayout.RightToLeft))
        if horizontal and not self._force_floating:
            idx = lay.indexOf(ts)
            if idx != -1:
                lay.insertWidget(idx, self)   # タイムスライダーの直前(左)へ挿入
                self._dock_mode = "layout"
                self.show()
                return
        # フォールバック: フローティング表示
        #   Maya のタイムスライダー(timeControl)は独自フォームでQtレイアウトを持たず、
        #   子ウィジェットは親領域外(左の負座標)だとクリップされて見えない。
        #   そのため独立ウィンドウ(Tool)としてタイムスライダーの左隣/直上に固定表示する。
        self._dock_mode = "floating"
        self.setParent(ts.window())
        self.setWindowFlags(QtCore.Qt.Tool |
                            QtCore.Qt.FramelessWindowHint |
                            QtCore.Qt.WindowStaysOnTopHint |
                            QtCore.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        try:
            ts.installEventFilter(self)
        except Exception:
            pass
        # ウィンドウ移動/リサイズに追従（専用イベントが拾えない場合の保険）
        self._pos_timer = QtCore.QTimer(self)
        self._pos_timer.timeout.connect(self._reposition)
        self._pos_timer.start(500)
        self._reposition()
        self.show()
        self.raise_()

    def _panel_width(self):
        w = self.sizeHint().width()
        fallback = PANEL_BTN_SIZE * 2 + PANEL_PLUS_SIZE + PANEL_SLIDER_W * 3 + 14 + 8 * 7
        return w if w > 40 else fallback

    def set_docked(self, flag):
        """ドッキング（タイムスライダー横に追従）/ 独立フロートの切り替え。"""
        self._docked = bool(flag)
        if self._docked:
            self._reposition()   # 再ドック時はスナップ

    def _docked_geometry(self):
        """ドッキング時のターゲット矩形 (x, y, w, h) をグローバル座標で返す。"""
        ts = self._timeslider
        if ts is None or self._dock_mode != "floating":
            return None
        try:
            if not ts.isVisible():
                return None
            h = ts.height()
            w = self._panel_width()
            gp = ts.mapToGlobal(QtCore.QPoint(0, 0))
            x = gp.x() - w                 # 基本はタイムスライダーの左隣
            if x < 0:                      # 左に余地が無ければ直上へ
                x = gp.x()
                y = gp.y() - h - 2
            else:
                y = gp.y()
            return int(x), int(y), int(w), int(h)
        except Exception:
            return None

    def _reposition(self):
        if self._dock_mode != "floating" or not self._docked:
            return
        geo = self._docked_geometry()
        if geo is None:
            return
        x, y, w, h = geo
        self.setFixedHeight(h)
        self.setGeometry(x, y, w, h)

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Move,
                            QtCore.QEvent.Show):
            self._reposition()
        return False

    # ----- 後始末 -----
    def cleanup(self):
        try:
            hide_overlay()
        except Exception:
            pass
        if self._add_dialog is not None:
            try:
                self._add_dialog.close()
                self._add_dialog.deleteLater()
            except Exception:
                pass
            self._add_dialog = None
        if self._pos_timer is not None:
            try:
                self._pos_timer.stop()
            except Exception:
                pass
            self._pos_timer = None
        ts = self._timeslider
        if ts is not None:
            try:
                ts.removeEventFilter(self)
            except Exception:
                pass
        p = self.parent()
        if self._dock_mode == "layout" and p is not None:
            lay = p.layout()
            if lay is not None:
                try:
                    lay.removeWidget(self)
                except Exception:
                    pass
        self.setParent(None)
        self.deleteLater()


def set_inset(left, right=None):
    """帯の水平位置合わせ用インセット(px)をライブ更新する。

    タイムスライダーの実描画領域はウィジェット幅より左右に少し内側にあるため、
    その内側余白(px)を左右に与えると、帯がフレーム目盛りにぴったり合う。
    「中央で合うが左右に行くほど対称にズレる」場合はこの値で調整する。

        tsbl.set_inset(8)       # 左右とも 8px
        tsbl.set_inset(8, 6)    # 左 8px / 右 6px

    現在値は (MARGIN_L, MARGIN_R)。
    """
    global MARGIN_L, MARGIN_R
    MARGIN_L = int(left)
    MARGIN_R = int(left if right is None else right)
    _ov_set('inset_l', MARGIN_L)      # 再起動後も保持
    _ov_set('inset_r', MARGIN_R)
    if _INSTANCE is not None:
        _INSTANCE.update()
    return (MARGIN_L, MARGIN_R)


def _show_dockable(win, ui_script):
    """MayaQWidgetDockableMixin の show を uiScript 付き(=次回起動で復元可)で呼ぶ。"""
    try:
        if ui_script:
            win.show(dockable=True, retain=False, uiScript=ui_script)
        else:
            win.show(dockable=True, retain=False)
    except Exception:
        try:
            win.show(dockable=True)
        except Exception:
            win.show()


def _restore_ws(kind):
    """workspaceControl 復元(uiScript)時に、現在の親へ中身を再構築する。
    Maya 起動時の自動復元でも呼ばれる（ドック位置/タブは Maya が記憶）。"""
    global _PANEL, MARGIN_L, MARGIN_R
    try:
        # インセット(保存値)を復元
        _il = _ov_get('inset_l', None)
        if _il is not None:
            MARGIN_L = int(_il)
            MARGIN_R = int(_ov_get('inset_r', _il))
        ts = _get_timeslider_widget()
        ptr = omui.MQtUtil.getCurrentParent()
        parent = wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None
        if parent is None:
            return
        lay = parent.layout()
        if lay is None:
            lay = QtWidgets.QVBoxLayout(parent)
            lay.setContentsMargins(0, 0, 0, 0)
        if kind == "control":
            panel = BookmarkControlPanel(
                ts, bottom_ratio=_WS_PARAMS.get("bottom_ratio", DEFAULT_BOTTOM_RATIO),
                mode="workspace", parent=parent)
            lay.addWidget(panel)
            _PANEL = panel
        else:
            lay.addWidget(ColorTab())
    except Exception as e:
        try:
            cmds.warning(u"UI復元に失敗: %s" % e)
        except Exception:
            pass


def show_controls(bottom_ratio=DEFAULT_BOTTOM_RATIO, inset=None,
                  dockable=True, force_floating=False, persist=True):
    """コントロールUIを表示。

    bottom_ratio   : 帯のタイムスライダー下端からの余白の割合（縦位置微調整）。既定 0.02。
    inset          : 帯の水平位置合わせ用インセット(px)。int/(left,right)。省略時は保存値/現状。
    dockable       : True(既定) = Maya標準の workspaceControl として表示。
                     False = タイムスライダー横にフローティング配置（旧方式）。
    force_floating : dockable=False の時のみ有効。
    persist        : True(既定) = ドッキング位置・タブ状態・開いていたタブを Maya のワークスペースに
                     記憶し、次回 Maya 起動時に前回の位置で自動復元する。
                     既に表示中（復元済み含む）なら作り直さず前面に出す（位置を保持）。
    """
    global _PANEL, _WIN, _WIN_COLOR, MARGIN_L, MARGIN_R

    # インセット（引数 > 保存値）の反映
    if inset is not None:
        if isinstance(inset, (tuple, list)) and len(inset) == 2:
            set_inset(inset[0], inset[1])
        else:
            set_inset(inset)
    else:
        _il = _ov_get('inset_l', None)
        if _il is not None:
            MARGIN_L = int(_il)
            MARGIN_R = int(_ov_get('inset_r', _il))

    ts = _get_timeslider_widget()
    if ts is None:
        cmds.warning("タイムスライダーが取得できませんでした。")
        return None

    if not dockable:
        hide_controls()
        _PANEL = BookmarkControlPanel(ts, bottom_ratio=bottom_ratio,
                                      force_floating=force_floating, mode="floating")
        return _PANEL

    _WS_PARAMS["bottom_ratio"] = bottom_ratio

    # persist=False（記憶しない）→ 旧 mixin 版が残っていれば掃除してから、uiScript 無しで新規作成
    if not persist:
        hide_controls()
        _create_ws_controls(persist=False)
        return _PANEL

    # persist=True: Maya ネイティブの workspaceControl(uiScript)方式。
    #   ・既に存在（前回ドック位置/タブで Maya が復元済み含む）→ 作り直さず復元/前面表示（位置・タブ保持）
    #   ・無ければ新規作成し、uiScript にモジュール絶対パスを焼き込み次回起動時に自動復元
    try:
        already = cmds.workspaceControl(WORKSPACE_CONTROL_NAME, q=True, exists=True)
    except Exception:
        already = False

    if already:
        for nm in (WORKSPACE_CONTROL_NAME, COLOR_CONTROL_NAME):
            try:
                if cmds.workspaceControl(nm, q=True, exists=True):
                    cmds.workspaceControl(nm, e=True, restore=True)
            except Exception:
                try:
                    cmds.workspaceControl(nm, e=True, vis=True)
                except Exception:
                    pass
        try:
            cmds.workspaceControl(WORKSPACE_CONTROL_NAME, e=True, r=True)
        except Exception:
            pass
        if _PANEL is not None and _INSTANCE is None:
            try:
                if _PANEL.barBtn.isChecked():
                    _PANEL._apply_show()
            except Exception:
                pass
        return _PANEL

    # 旧 mixin 版のゴミが残っていれば掃除して新規作成
    hide_controls()
    _create_ws_controls(persist=True)
    return _PANEL


def _create_ws_controls(persist=True):
    """バーコントロール／カラーの workspaceControl を新規作成し、タブ結合する。

    persist=True の時のみ uiScript を仕込む（＝Maya 再起動時に自動復元）。
    uiScript が Maya に内容を構築させるため、ここでは workspaceControl を作るだけ。
    """
    ui_ctrl = _uiscript("control") if persist else ""
    ui_color = _uiscript("color") if persist else ""

    kw_ctrl = dict(label=u"BM バーコントロール", retain=False, floating=True,
                   initialWidth=240, initialHeight=110)
    kw_color = dict(label=u"カラー", retain=False, floating=True,
                    initialWidth=240, initialHeight=110)
    if persist:
        kw_ctrl["uiScript"] = ui_ctrl
        kw_color["uiScript"] = ui_color

    cmds.workspaceControl(WORKSPACE_CONTROL_NAME, **kw_ctrl)
    # uiScript 無し(persist=False)のときは Maya が中身を呼ばないので手動構築
    if not persist:
        _build_ws_content(WORKSPACE_CONTROL_NAME, "control")

    cmds.workspaceControl(COLOR_CONTROL_NAME, **kw_color)
    if not persist:
        _build_ws_content(COLOR_CONTROL_NAME, "color")

    # 2枚を Maya 標準ドックの同一タブ列に結合（Maya が結合状態とアクティブタブを記憶）
    try:
        cmds.workspaceControl(COLOR_CONTROL_NAME, e=True,
                              tabToControl=(WORKSPACE_CONTROL_NAME, -1))
    except Exception as ex:
        cmds.warning(u"カラータブの結合に失敗（手動でタブ化してください）: %s" % ex)
    try:
        cmds.workspaceControl(WORKSPACE_CONTROL_NAME, e=True, r=True)
    except Exception:
        pass


def _build_ws_content(control_name, kind):
    """uiScript を使わない場合に、指定 workspaceControl の中身を構築する。"""
    try:
        cmds.setParent(control_name)
    except Exception:
        pass
    _restore_ws(kind)


def debug_persist():
    """永続化まわりの状態を出力する診断用。復元されない時はこの出力を送ってください。"""
    def _ex(nm):
        try:
            return bool(cmds.workspaceControl(nm, q=True, exists=True))
        except Exception as e:
            return "err:%s" % e

    def _uis(nm):
        try:
            return cmds.workspaceControl(nm, q=True, uiScript=True)
        except Exception as e:
            return "err:%s" % e

    print(u"===== TimeSliderBookmarkBar 永続化診断 =====")
    print(u"module name : %s" % _module_name())
    print(u"module dir  : %s" % _module_dir())
    print(u"dir on sys.path : %s" % (_module_dir() in sys.path))
    for nm in (WORKSPACE_CONTROL_NAME, COLOR_CONTROL_NAME,
               _WS_MIXIN_CONTROL, _COLOR_MIXIN_CONTROL):
        print(u"  [%s] exists=%s" % (nm, _ex(nm)))
    print(u"  uiScript(control):\n%s" % _uis(WORKSPACE_CONTROL_NAME))
    print(u"  uiScript(color):\n%s" % _uis(COLOR_CONTROL_NAME))
    print(u"===========================================")


def _make_dockable_window(kind, ts, bottom_ratio):
    """MayaQWidgetDockableMixin を使ったドッキング可能ウィンドウを生成して返す。
    kind: 'control'（バーコントロール）/ 'color'（カラー）。
    mixin が使えない環境では None（呼び出し側が uiScript 版へフォールバック）。"""
    try:
        from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
    except Exception:
        return None

    if kind == "control":
        obj_name = WORKSPACE_CONTROL_NAME
        title = u"バーコントロール"
    else:
        obj_name = COLOR_CONTROL_NAME
        title = u"カラー"

    class _BookmarkDockWindow(MayaQWidgetDockableMixin, QtWidgets.QWidget):
        def __init__(self, parent=None):
            super(_BookmarkDockWindow, self).__init__(parent=parent)
            self.setObjectName(obj_name)
            self.setWindowTitle(title)
            l = QtWidgets.QVBoxLayout(self)
            l.setContentsMargins(0, 0, 0, 0)
            l.setSpacing(0)
            if kind == "control":
                self._panel = BookmarkControlPanel(
                    ts, bottom_ratio=bottom_ratio, mode="workspace")
                l.addWidget(self._panel)
            else:
                self._panel = None
                l.addWidget(ColorTab())

    try:
        return _BookmarkDockWindow()
    except Exception as e:
        cmds.warning(u"ドッキングウィンドウ生成に失敗（uiScript版へ）: %s" % e)
        return None


def _build_workspace_ui():
    """workspaceControl の uiScript から呼ばれ、現在の親にパネルを構築する（フォールバック）。"""
    global _PANEL
    ts = _get_timeslider_widget()
    parent = None
    try:
        ptr = omui.MQtUtil.getCurrentParent()
        if ptr is not None:
            parent = wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        parent = None
    panel = BookmarkControlPanel(
        ts, bottom_ratio=_WS_PARAMS.get("bottom_ratio", DEFAULT_BOTTOM_RATIO),
        mode="workspace", parent=parent)
    if parent is not None:
        lay = parent.layout()
        if lay is None:
            lay = QtWidgets.QVBoxLayout(parent)
            lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(panel)
    _PANEL = panel
    return panel


def hide_controls():
    """コントロールUIとオーバーレイをまとめて消す。"""
    global _PANEL, _WIN, _WIN_COLOR, _DELETE_MODE
    _DELETE_MODE = False
    if _PANEL is not None:
        try:
            _PANEL.cleanup()
        except Exception:
            pass
        _PANEL = None
    for _w in (_WIN, _WIN_COLOR):
        if _w is not None:
            try:
                _w.close()
                _w.deleteLater()
            except Exception:
                pass
    _WIN = None
    _WIN_COLOR = None
    hide_overlay()
    # workspaceControl の削除（メイン/カラー、手動版・mixin版の名前すべて）
    for nm in (WORKSPACE_CONTROL_NAME, _WS_MIXIN_CONTROL,
               COLOR_CONTROL_NAME, _COLOR_MIXIN_CONTROL):
        try:
            if cmds.workspaceControl(nm, q=True, exists=True):
                cmds.deleteUI(nm)
        except Exception:
            pass
    # reload等でorphanになったパネル（旧フロート含む）を確実に掃除。
    # ※reloadすると _PANEL 参照は失われるが、Qt側には残るため二重表示になる問題への対処。
    #   全ウィジェットを走査し、同名(objectName)のパネルを破棄する。
    try:
        for w in list(QtWidgets.QApplication.allWidgets()):
            try:
                if w is not None and w.objectName() == PANEL_OBJECT_NAME:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
            except Exception:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    show_controls()
