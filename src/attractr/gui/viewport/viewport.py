"""The main image view: shows the progressive preview, handles camera interaction, HUD."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QWidget

from attractr.core.math import quaternion as Q
from attractr.core.render.result import RenderResult
from attractr.gui.state.document import Document

ROTATE_DEG_PER_PX = 0.4


class Viewport(QWidget):
    viewResized = Signal(int, int)
    hoverInfo = Signal(str)
    dropRequested = Signal(object)  # QMimeData dropped onto the image (handled by the main window)

    def __init__(self, document: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = document
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(120, 90)
        self._image: QImage | None = None
        self._result: RenderResult | None = None
        self._drag_button: Qt.MouseButton | None = None
        self._last_pos = QPoint()
        self._cam_start = None
        self.show_hud = True
        self.hud_lines: list[str] = []
        self.caption_lines: list[str] = []
        self.spin_timer = QTimer(self)
        self.spin_timer.setInterval(33)
        self.spin_timer.timeout.connect(self._spin_step)
        self.spin_speed = 0.6  # degrees per tick
        self._zoom_acc = 0.0

    # ── data in ─────────────────────────────────────────────────────────────────
    def set_image(self, img: QImage, result: RenderResult | None) -> None:
        self._image = img
        self._result = result
        self.update()

    def set_hud(self, lines: list[str]) -> None:
        self.hud_lines = lines
        self.update()

    # ── geometry ───────────────────────────────────────────────────────────────
    def image_rect(self) -> QRectF:
        """Where the image is drawn (letter-boxed, aspect preserved)."""
        if self._image is None or self._image.isNull():
            return QRectF(0, 0, self.width(), self.height())
        iw, ih = self._image.width(), self._image.height()
        s = min(self.width() / iw, self.height() / ih)
        w, h = iw * s, ih * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self.viewResized.emit(self.width(), self.height())

    # ── drag & drop ────────────────────────────────────────────────────────────
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        from attractr.gui.dragdrop import can_accept

        if can_accept(e.mimeData()):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        self.dropRequested.emit(e.mimeData())
        e.acceptProposedAction()

    # ── painting ───────────────────────────────────────────────────────────────
    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(12, 12, 16))
        if self._image is not None and not self._image.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(self.image_rect(), self._image)
        else:
            p.setPen(QColor(120, 120, 140))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "rendering preview…")
        if self.show_hud and self.hud_lines:
            self._draw_text_block(p, self.hud_lines, 10, 10, align_bottom=False)
        if self.caption_lines:
            self._draw_text_block(p, self.caption_lines, 10, self.height() - 10, align_bottom=True)
        p.end()

    def _draw_text_block(self, p: QPainter, lines: list[str], x: int, y: int, align_bottom: bool) -> None:
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        font.setPointSize(9)
        p.setFont(font)
        fm = p.fontMetrics()
        lh = fm.height()
        w = max((fm.horizontalAdvance(t) for t in lines), default=0) + 12
        h = lh * len(lines) + 8
        top = y - h if align_bottom else y
        p.fillRect(QRectF(x - 4, top, w, h), QColor(0, 0, 0, 140))
        p.setPen(QColor(220, 225, 235))
        for i, t in enumerate(lines):
            p.drawText(QPointF(x + 2, top + 4 + fm.ascent() + i * lh), t)

    # ── interaction ────────────────────────────────────────────────────────────
    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        self._drag_button = e.button()
        self._last_pos = e.position().toPoint()
        self._cam_start = self.doc.settings.camera
        self.doc.begin_interaction()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        self._drag_button = None
        self.doc.end_interaction()
        self.unsetCursor()

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        self.doc.reset_camera()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        pos = e.position().toPoint()
        if self._drag_button is None:
            self._probe(pos)
            return
        dx = pos.x() - self._last_pos.x()
        dy = pos.y() - self._last_pos.y()
        self._last_pos = pos
        cam = self.doc.settings.camera
        mods = e.modifiers()
        pan_mode = self._drag_button == Qt.MouseButton.MiddleButton or bool(mods & Qt.KeyboardModifier.ShiftModifier) or not self.doc.spec.is_3d
        if pan_mode:
            r = self.image_rect()
            cam = replace(cam, pan_u=cam.pan_u + dx / max(r.width(), 1), pan_v=cam.pan_v + dy / max(r.height(), 1))
        elif self._drag_button == Qt.MouseButton.RightButton:
            cam = cam.rotated_by(Q.from_axis_angle((0.0, 0.0, 1.0), -dx * ROTATE_DEG_PER_PX))
        else:
            dq = Q.multiply(Q.from_axis_angle((0.0, 1.0, 0.0), dx * ROTATE_DEG_PER_PX),
                            Q.from_axis_angle((1.0, 0.0, 0.0), dy * ROTATE_DEG_PER_PX))
            cam = cam.rotated_by(dq)
        self.doc.set_camera(cam, interactive=True)

    def wheelEvent(self, e: QWheelEvent) -> None:  # noqa: N802
        delta = e.angleDelta().y() / 120.0
        if delta == 0:
            return
        factor = 1.12**delta
        cam = self.doc.settings.camera
        r = self.image_rect()
        # keep the point under the cursor fixed: pan is in fractions of the image
        px = (e.position().x() - r.center().x()) / max(r.width(), 1)
        py = (e.position().y() - r.center().y()) / max(r.height(), 1)
        new_pan_u = px - (px - cam.pan_u) * factor
        new_pan_v = py - (py - cam.pan_v) * factor
        cam = replace(cam, zoom=float(np.clip(cam.zoom * factor, 0.05, 200.0)), pan_u=new_pan_u, pan_v=new_pan_v)
        self.doc.begin_interaction()
        self.doc.set_camera(cam, interactive=True, text="Zoom")
        QTimer.singleShot(150, self.doc.end_interaction)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Space:
            self.toggle_spin()
        elif e.key() == Qt.Key.Key_H:
            self.show_hud = not self.show_hud
            self.update()
        else:
            super().keyPressEvent(e)

    def toggle_spin(self) -> None:
        if self.spin_timer.isActive():
            self.spin_timer.stop()
            self.doc.end_interaction()
        else:
            self.doc.begin_interaction()
            self.spin_timer.start()

    def _spin_step(self) -> None:
        cam = self.doc.settings.camera.rotated_by(Q.from_axis_angle((0.0, 1.0, 0.0), self.spin_speed))
        self.doc.set_camera(cam, interactive=True, text="Spin")

    # ── pixel probe ────────────────────────────────────────────────────────────
    def _probe(self, pos: QPoint) -> None:
        res = self._result
        if res is None or self._image is None:
            return
        r = self.image_rect()
        if not r.contains(QPointF(pos)):
            self.hoverInfo.emit("")
            return
        x = int((pos.x() - r.left()) / r.width() * res.width)
        y = int((pos.y() - r.top()) / r.height() * res.height)
        x = min(max(x, 0), res.width - 1)
        y = min(max(y, 0), res.height - 1)
        c = float(res.count[y, x])
        parts = [f"px ({x}, {y})", f"count {c:.1f}"]
        if res.stats.percentile_count:
            parts.append(f"density {np.log1p(c) / np.log1p(res.stats.percentile_count):.3f}")
        md = res.mean_depth()
        if md is not None and c > 0:
            parts.append(f"depth {md[y, x]:+.3f}")
        cv = res.mean_cv()
        if cv is not None and c > 0:
            parts.append(f"colour value {cv[y, x]:+.3f}")
        self.hoverInfo.emit(" · ".join(parts))
