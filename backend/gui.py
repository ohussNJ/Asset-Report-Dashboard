# gui.py  –  PyQt6 GUI for Asset Report Dashboard

import math
import numpy as np
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QScrollArea, QFrame, QButtonGroup,
    QDialog, QLineEdit, QDialogButtonBox, QSizePolicy, QGridLayout,
    QSpinBox, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui import QFont, QCursor, QPainter, QPen, QColor, QPainterPath, QFontMetrics
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

import data as Data
import indicators
import signals as Sig
import charts as Charts
import backtest as BT
from config import TICKERS, WATCHLIST, STOCHRSI_CONFIGS, MA_PERIODS, LOOKBACK_OPTIONS, DEFAULT_LOOKBACK

# ── Colors ────────────────────────────────────────────────────────────────────
BG      = "#1a1a1a"
BG_CARD = "#242424"
BG_TOP  = "#1e1e1e"
FG      = "#e0e0e0"
FG_SUB  = "#888888"
BULL_BG = "#1a3a2a"; BULL_FG = "#4ade80"
BEAR_BG = "#3a1a1a"; BEAR_FG = "#f87171"
NEUT_BG = "#2a2a2a"; NEUT_FG = "#9ca3af"

CARD_W = 280   # fixed card width


def _sig_colors(bull):
    if bull is True:  return BULL_BG, BULL_FG
    if bull is False: return BEAR_BG, BEAR_FG
    return NEUT_BG, NEUT_FG


# ── Widget helpers ────────────────────────────────────────────────────────────

def _lbl(text, color=FG, size=9, bold=False, mono=False):
    w = QLabel(text)
    w.setFont(QFont("Consolas" if mono else "Segoe UI", size,
                    QFont.Weight.Bold if bold else QFont.Weight.Normal))
    w.setStyleSheet(f"color:{color}; background:transparent;")
    return w


def _seg_btn(text, checked=False):
    b = QPushButton(text)
    b.setCheckable(True)
    b.setChecked(checked)
    b.setFixedHeight(26)
    b.setFont(QFont("Segoe UI", 9))
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    def _restyle(c=None, btn=b):
        if btn.isChecked():
            btn.setStyleSheet(
                "QPushButton{background:#3a3a5a;color:#e0e0e0;"
                "border:1px solid #5a5a8a;border-radius:4px;padding:0 10px;}"
            )
        else:
            btn.setStyleSheet(
                "QPushButton{background:#2a2a2a;color:#888;border:1px solid #3a3a3a;"
                "border-radius:4px;padding:0 10px;}"
                "QPushButton:hover{background:#333;color:#ccc;}"
            )
    _restyle()
    b.toggled.connect(_restyle)
    return b


def _btn(text, bg="#3a3a3a", hover="#4a4a4a", fg=FG, w=None, h=26):
    b = QPushButton(text)
    b.setFixedHeight(h)
    if w:
        b.setFixedWidth(w)
    b.setFont(QFont("Segoe UI", 9))
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    b.setStyleSheet(
        f"QPushButton{{background:{bg};color:{fg};border:1px solid #555;"
        f"border-radius:4px;padding:0 10px;}}"
        f"QPushButton:hover{{background:{hover};}}"
        f"QPushButton:disabled{{background:#2a2a2a;color:#555;border-color:#333;}}"
    )
    return b


def _hsep():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet("background:#1a1a1a;")
    return f


def _build_signal_history_widget(df, inline=False) -> "QWidget | None":
    """Current + previous signal state block (used in cards and watchlist rows)."""
    if df is None or df.empty:
        return None
    try:
        hist = Sig.signal_state_history(df, n=len(df))
    except Exception:
        return None
    if len(hist) < 2:
        return None

    # Build contiguous segments from the state series
    segments = []
    cur_state = hist.iloc[0]
    cur_start = hist.index[0]
    for i in range(1, len(hist)):
        if hist.iloc[i] != cur_state:
            segments.append((cur_state, cur_start, hist.index[i - 1]))
            cur_state = hist.iloc[i]
            cur_start = hist.index[i]
    segments.append((cur_state, cur_start, hist.index[-1]))

    if not segments:
        return None

    def _fmt_date(ts):
        return f"{ts.strftime('%b')} {ts.day}"

    def _state_fg(state):
        if state == "BULL":    return BULL_FG
        if state == "BEAR":    return BEAR_FG
        return NEUT_FG

    def _state_bg(state):
        if state == "BULL":    return BULL_BG
        if state == "BEAR":    return BEAR_BG
        return NEUT_BG

    def _make_row(label, state, start, end, is_today=False):
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 2, 8, 2)
        rl.setSpacing(6)

        lbl_w = _lbl(label, color=FG_SUB, size=8)
        lbl_w.setFixedWidth(54)
        rl.addWidget(lbl_w)

        badge = QLabel(state)
        badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(58, 18)
        badge.setStyleSheet(
            f"color:{_state_fg(state)};background:{_state_bg(state)};"
            f"border-radius:3px;padding:0 4px;")
        rl.addWidget(badge)

        bars = int(((hist.index >= start) & (hist.index <= end)).sum())
        end_str  = "today" if is_today else _fmt_date(end)
        date_str = f"{_fmt_date(start)} – {end_str}  ({bars}d)"
        rl.addWidget(_lbl(date_str, color=FG_SUB, size=8, mono=True))

        return row

    w = QWidget()
    w.setStyleSheet("background:transparent;")

    if inline:
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        cur = segments[-1]
        layout.addWidget(_make_row("Current:", cur[0], cur[1], cur[2], is_today=True))
        if len(segments) >= 2:
            prev = segments[-2]
            sep = _lbl("  |  ", color="#444", size=8)
            layout.addWidget(sep)
            layout.addWidget(_make_row("Previous:", prev[0], prev[1], prev[2]))
    else:
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(1)
        cur = segments[-1]
        layout.addWidget(_make_row("Current:", cur[0], cur[1], cur[2], is_today=True))
        if len(segments) >= 2:
            prev = segments[-2]
            layout.addWidget(_make_row("Previous:", prev[0], prev[1], prev[2]))

    return w


def _attach_crosshair(canvas):
    """Vertical crosshair on all axes; horizontal crosshair on whichever axis the mouse is in."""
    axes = canvas.figure.get_axes()
    if not axes:
        return

    vlines = [
        ax.axvline(x=axes[0].get_xlim()[0], color="#6666aa", lw=0.8,
                   linestyle="--", alpha=0.5, visible=False, zorder=20)
        for ax in axes
    ]
    hlines = {
        ax: ax.axhline(y=ax.get_ylim()[0], color="#6666aa", lw=0.8,
                       linestyle="--", alpha=0.5, visible=False, zorder=20)
        for ax in axes
    }

    def on_move(event):
        if event.inaxes is None or event.xdata is None:
            for vl in vlines:
                vl.set_visible(False)
            for hl in hlines.values():
                hl.set_visible(False)
            canvas.draw_idle()
            return
        for vl in vlines:
            vl.set_xdata([event.xdata, event.xdata])
            vl.set_visible(True)
        for ax, hl in hlines.items():
            if ax is event.inaxes and event.ydata is not None:
                hl.set_ydata([event.ydata, event.ydata])
                hl.set_visible(True)
            else:
                hl.set_visible(False)
        canvas.draw_idle()

    def on_leave(event):
        for vl in vlines:
            vl.set_visible(False)
        for hl in hlines.values():
            hl.set_visible(False)
        canvas.draw_idle()

    canvas.mpl_connect("motion_notify_event", on_move)
    canvas.mpl_connect("figure_leave_event", on_leave)


# ── Sparkline widget ─────────────────────────────────────────────────────────

class _ScoreSparkline(QWidget):
    """Score history sparkline with ±20 neutral-zone lines to mirror Pine's scoreSmooth plot."""
    def __init__(self, values, parent=None):
        super().__init__(parent)
        self._vals = list(values)
        self.setFixedHeight(44)

    def paintEvent(self, event):
        if len(self._vals) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad_x, pad_y = 4, 4
        w = self.width()  - 2 * pad_x
        h = self.height() - 2 * pad_y

        # Fixed y range: -70 to +70 (max possible score)
        y_min, y_max = -70.0, 70.0
        rng = y_max - y_min

        def _y(v):
            return pad_y + (1.0 - (v - y_min) / rng) * h

        n = len(self._vals)

        # ±20 neutral zone fill
        y_plus20  = _y( 20)
        y_minus20 = _y(-20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(60, 60, 60, 60))
        p.drawRect(QRectF(pad_x, y_plus20, w, y_minus20 - y_plus20))

        # Zero line
        p.setPen(QPen(QColor("#555555"), 0.8, Qt.PenStyle.DotLine))
        y0 = _y(0)
        p.drawLine(int(pad_x), int(y0), int(pad_x + w), int(y0))

        # Score line colored by current value
        last = self._vals[-1]
        line_color = BULL_FG if last > 20 else BEAR_FG if last < -20 else NEUT_FG
        path = QPainterPath()
        for i, v in enumerate(self._vals):
            x = pad_x + i / (n - 1) * w
            y = _y(v)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        p.setPen(QPen(QColor(line_color), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        p.end()


# ── Scrolling ticker banner ───────────────────────────────────────────────────

class _ScrollBanner(QWidget):
    """Horizontally scrolling marquee showing bullish tickers and their scores."""
    def __init__(self, items: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        # items: [(name, score_str), ...]  filtered to bullish only
        self._font  = QFont("Consolas", 9, QFont.Weight.Bold)
        self._sep   = "   ·   "
        self._text  = self._sep.join(f"{n}  {s}" for n, s in items)
        self._text += "   |   "  # loop divider
        self._offset = 0.0
        self._speed  = 0.6        # px per timer tick
        self.setFixedHeight(28)

        fm = QFontMetrics(self._font)
        self._text_w = fm.horizontalAdvance(self._text)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)     # ~60 fps

    def _tick(self):
        self._offset += self._speed
        if self._text_w > 0 and self._offset >= self._text_w:
            self._offset -= self._text_w
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#1a1a1a"))
        p.setFont(self._font)
        p.setPen(QColor(BULL_FG))
        y = int((self.height() + QFontMetrics(self._font).ascent()
                 - QFontMetrics(self._font).descent()) / 2)
        x = -self._offset
        while x < self.width():
            p.drawText(int(x), y, self._text)
            x += self._text_w
        p.end()

    def stop(self):
        self._timer.stop()


# ── Responsive flow grid ──────────────────────────────────────────────────────

class _FlowGrid(QWidget):
    """Places fixed-width cards into a responsive grid that reflows on resize."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[QWidget] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(6, 6, 6, 6)
        self._grid.setSpacing(8)
        self._cols = 0

    def add_card(self, card: QWidget):
        self._cards.append(card)
        self._reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self):
        if not self._cards:
            return
        cols = max(1, self.width() // (CARD_W + 8))
        if cols == self._cols:
            return
        self._cols = cols
        while self._grid.count():
            self._grid.takeAt(0)
        for i, card in enumerate(self._cards):
            self._grid.addWidget(card, i // cols, i % cols,
                                 Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)


# ── Worker thread ─────────────────────────────────────────────────────────────

class _Worker(QThread):
    status  = pyqtSignal(str)
    done    = pyqtSignal()
    errored = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self._fn()
            self.done.emit()
        except Exception as exc:
            self.errored.emit(str(exc))


# ── Main window ───────────────────────────────────────────────────────────────

class AssetReportApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Asset Report")
        self.resize(1500, 920)
        self.setStyleSheet(f"QMainWindow{{background:{BG};}}")

        self._interval = "1d"
        self._lookback = DEFAULT_LOOKBACK["1d"]
        self._daily:         dict = {}
        self._weekly:        dict = {}
        self._computed:      dict = {}
        self._sig:           dict = {}
        self._custom:        list = []
        self._watchlist_sig: dict = {}
        self._watchlist_df:  dict = {}
        self._worker:        _Worker | None = None
        self._vix:           float | None = None
        self._move:          float | None = None
        self._move_slope:    float | None = None
        self._banner:             "_ScrollBanner | None" = None
        self._rendered_tabs:      set  = set()
        self._switching_interval: bool = False

        self._build_ui()
        QTimer.singleShot(200, self._refresh)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        top = QFrame()
        top.setFixedHeight(44)
        top.setStyleSheet(f"background:{BG_TOP};border-bottom:1px solid #333;")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(12, 0, 12, 0)
        tl.setSpacing(6)

        tl.addWidget(_lbl("Asset Report", bold=True, size=11))
        tl.addSpacing(8)

        # Interval
        self._btn_daily  = _seg_btn("Daily",  checked=True)
        self._btn_weekly = _seg_btn("Weekly", checked=False)
        iv_grp = QButtonGroup(self); iv_grp.setExclusive(True)
        iv_grp.addButton(self._btn_daily)
        iv_grp.addButton(self._btn_weekly)
        self._btn_daily.toggled.connect( lambda c: c and self._on_interval("Daily"))
        self._btn_weekly.toggled.connect(lambda c: c and self._on_interval("Weekly"))
        tl.addWidget(self._btn_daily)
        tl.addWidget(self._btn_weekly)
        tl.addSpacing(6)

        # Lookback
        self._lb_btns: dict[str, QPushButton] = {}
        lb_grp = QButtonGroup(self); lb_grp.setExclusive(True)
        for key in LOOKBACK_OPTIONS:
            b = _seg_btn(key, checked=(key == DEFAULT_LOOKBACK["1d"]))
            lb_grp.addButton(b)
            self._lb_btns[key] = b
            b.toggled.connect(lambda c, k=key: c and self._on_lookback(k))
            tl.addWidget(b)
        tl.addSpacing(6)

        ref = _btn("⟳  Refresh", w=90)
        ref.clicked.connect(self._refresh)
        tl.addWidget(ref)

        self._add_btn = _btn("＋ Ticker", w=85)
        self._add_btn.clicked.connect(self._prompt_add_ticker)
        tl.addWidget(self._add_btn)

        tl.addStretch()
        self._status_lbl = _lbl("Initializing…", color=FG_SUB)
        tl.addWidget(self._status_lbl)
        vbox.addWidget(top)

        # ── Tabs ──────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane  {{ background:{BG}; border:none; }}
            QTabBar::tab      {{ background:#242424; color:#888; padding:7px 16px;
                                 border:none; border-bottom:2px solid transparent;
                                 font-family:'Segoe UI'; font-size:9pt; }}
            QTabBar::tab:selected {{ color:#e0e0e0; background:#2e2e2e;
                                     border-bottom:2px solid #6060a0; }}
            QTabBar::tab:hover    {{ background:#2e2e2e; color:#ccc; }}
        """)

        for label in ["Summary", "Watchlist", "Backtest", "Info"] + list(TICKERS):
            self._tabs.addTab(QWidget(), label)

        self._build_info_tab()
        self._tabs.setCurrentIndex(self._tab_index("Summary"))

        mkt_card = QFrame()
        mkt_card.setStyleSheet(
            "QFrame{background:#242424;border:1px solid #333;"
            "border-radius:5px;margin:4px 8px 4px 0;}")
        mkt_hl = QHBoxLayout(mkt_card)
        mkt_hl.setContentsMargins(8, 0, 8, 0)
        mkt_hl.setSpacing(10)

        def _mkt_pair(label):
            mkt_hl.addWidget(_lbl(label, color="#888", size=8, bold=True))
            val_lbl = _lbl("—", color="#e0e0e0", size=9, mono=True)
            mkt_hl.addWidget(val_lbl)
            return val_lbl

        self._vix_lbl   = _mkt_pair("VIX")
        self._move_lbl  = _mkt_pair("MOVE")
        self._tabs.setCornerWidget(mkt_card)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        vbox.addWidget(self._tabs)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _tab_index(self, name: str) -> int:
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == name:
                return i
        return -1

    def _swap_tab(self, idx: int, widget: QWidget, label: str):
        old = self._tabs.widget(idx)
        self._tabs.removeTab(idx)
        self._tabs.insertTab(idx, widget, label)
        if old:
            old.deleteLater()

    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)

    def _scroll_wrap(self, inner: QWidget, bg=BG) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setStyleSheet(
            f"QScrollArea{{background:{bg};border:none;}}"
            "QScrollBar:vertical{background:#1a1a1a;width:12px;border-radius:6px;margin:2px;}"
            "QScrollBar::handle:vertical{background:#555;border-radius:5px;min-height:30px;}"
            "QScrollBar::handle:vertical:hover{background:#777;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        sa.setWidget(inner)
        return sa

    # ── Worker ────────────────────────────────────────────────────────────────

    def _run_worker(self, fn, on_done=None):
        if self._worker and self._worker.isRunning():
            return
        self._worker = _Worker(fn)
        self._worker.status.connect(self._set_status)
        self._worker.errored.connect(lambda e: self._set_status(f"Error: {e}"))
        self._worker.done.connect(on_done if on_done else self._render_all)
        self._worker.start()

    def _refresh(self):
        self._set_status("Fetching data…")
        self._run_worker(self._fetch_all_worker)

    def _fetch_all_worker(self):
        self._worker.status.emit("Fetching daily data…")
        self._daily  = Data.fetch_all("1d",  force=True)
        self._worker.status.emit("Fetching weekly data…")
        self._weekly = Data.fetch_all("1wk", force=True)
        self._worker.status.emit("Computing indicators…")
        self._compute()
        self._worker.status.emit("Computing watchlist…")
        self._compute_watchlist()
        try:
            mkt_batch   = Data.fetch_symbols_batch(["^VIX", "^MOVE"], "1d")
            vix_df      = mkt_batch.get("^VIX")
            move_df     = mkt_batch.get("^MOVE")
            self._vix   = float(vix_df["Close"].dropna().iloc[-1])  if vix_df  is not None and not vix_df.empty  else None
            if move_df is not None and not move_df.empty:
                move_close       = move_df["Close"].dropna()
                self._move       = float(move_close.iloc[-1])
                window           = move_close.iloc[-10:].values.astype(float)
                self._move_slope = float(np.polyfit(np.arange(len(window)), window, 1)[0]) if len(window) >= 2 else None
            else:
                self._move = self._move_slope = None
        except Exception:
            self._vix  = None
            self._move = None

    def _compute(self):
        self._computed = {}
        self._sig      = {}
        for name in list(TICKERS) + self._custom:
            dd = self._daily.get(name)
            dw = self._weekly.get(name)
            if dd is None or dd.empty:
                continue
            base = dd if self._interval == "1d" else (
                dw if dw is not None and not dw.empty else dd)
            comp = indicators.compute_all(base, dw if dw is not None else dd)
            self._computed[name] = comp
            self._sig[name]      = Sig.get_signals(comp)

    def _compute_watchlist(self):
        sym_to_sig = {}
        sym_to_df  = {}
        for key, sym in TICKERS.items():
            if key in self._sig:
                sym_to_sig[sym] = self._sig[key]
                sym_to_df[sym]  = self._computed.get(key)
        for sym in self._custom:
            if sym in self._sig:
                sym_to_sig[sym] = self._sig[sym]
                sym_to_df[sym]  = self._computed.get(sym)

        all_syms = [s for entries in WATCHLIST.values() for s in entries]
        to_fetch = [s for s in all_syms if s not in sym_to_sig]

        if to_fetch:
            d_batch = Data.fetch_symbols_batch(to_fetch, "1d")
            w_batch = Data.fetch_symbols_batch(to_fetch, "1wk")
        else:
            d_batch = w_batch = {}

        self._watchlist_sig = {}
        self._watchlist_df  = {}
        for sym in all_syms:
            if sym in sym_to_sig:
                self._watchlist_sig[sym] = sym_to_sig[sym]
                self._watchlist_df[sym]  = sym_to_df.get(sym)
                continue
            dd = d_batch.get(sym)
            dw = w_batch.get(sym)
            if dd is None or dd.empty:
                continue
            try:
                comp = indicators.compute_all(dd, dw if dw is not None and not dw.empty else dd)
                self._watchlist_sig[sym] = Sig.get_signals(comp)
                self._watchlist_df[sym]  = comp
            except Exception:
                pass

    def _on_interval(self, val: str):
        self._interval = "1d" if val == "Daily" else "1wk"
        new_lb = DEFAULT_LOOKBACK[self._interval]
        self._lookback = new_lb
        # Flag prevents _on_lookback from rendering with stale data while we
        # programmatically reset the lookback button. QButtonGroup still gets
        # to hear the toggled signal so it correctly unchecks the old button.
        self._switching_interval = True
        self._lb_btns[new_lb].setChecked(True)
        self._switching_interval = False
        if self._daily:
            self._run_worker(self._recompute_worker, on_done=self._render_interval_switch)

    def _recompute_worker(self):
        self._worker.status.emit("Recomputing…")
        self._compute()
        self._compute_watchlist()

    def _render_interval_switch(self):
        """Done callback for interval switches, mirrors _render_all's blockSignals
        pattern so _swap_tab's removeTab/insertTab don't cascade into _on_tab_changed
        and schedule stale-index QTimer.singleShot calls that navigate away from
        the current ticker."""
        self._rendered_tabs.clear()
        saved = self._tabs.currentIndex()
        self._tabs.blockSignals(True)
        self._render_summary()
        self._render_watchlist()
        cur_name = self._tabs.tabText(saved)
        if cur_name == "Backtest":
            self._render_backtest()
            self._rendered_tabs.add("Backtest")
        elif cur_name in list(TICKERS) + self._custom:
            self._render_ticker(cur_name)
            self._rendered_tabs.add(cur_name)
        self._tabs.blockSignals(False)
        self._tabs.setCurrentIndex(saved)
        if self._computed:
            last     = next(iter(self._computed.values()))
            date_str = last.index[-1].strftime("%Y-%m-%d")
            iv       = "Daily" if self._interval == "1d" else "Weekly"
            self._set_status(f"Updated  ·  {iv}  ·  last close {date_str}")
            self._add_btn.setEnabled(True)
            self._add_btn.setToolTip("")

    def _on_lookback(self, val: str):
        self._lookback = val
        if getattr(self, "_switching_interval", False):
            return
        if self._computed:
            self._rendered_tabs.clear()
            saved = self._tabs.currentIndex()
            cur_name = self._tabs.tabText(saved)
            self._tabs.blockSignals(True)
            if cur_name in list(TICKERS) + self._custom:
                self._render_ticker(cur_name)
                self._rendered_tabs.add(cur_name)
            self._tabs.blockSignals(False)
            self._tabs.setCurrentIndex(saved)

    # ── Render all ────────────────────────────────────────────────────────────

    def _render_all(self):
        if self._vix is not None:
            color = "#F38BA8" if self._vix >= 20 else "#A6E3A1" if self._vix < 15 else "#F9E2AF"
            self._vix_lbl.setText(f"{self._vix:.1f}")
            self._vix_lbl.setStyleSheet(f"color:{color};font-family:Consolas;font-size:9pt;")
        if self._move is not None:
            if self._move_slope is not None:
                color = "#F38BA8" if self._move_slope > 0 else "#A6E3A1" if self._move_slope < 0 else "#e0e0e0"
            else:
                color = "#e0e0e0"
            self._move_lbl.setText(f"{self._move:.0f}")
            self._move_lbl.setStyleSheet(f"color:{color};font-family:Consolas;font-size:9pt;")
        # Invalidate all ticker tabs so they re-render on next selection
        self._rendered_tabs.clear()
        saved = self._tabs.currentIndex()
        # Keep signals blocked for the entire render pass (Summary, Watchlist,
        # and the current ticker).  Each _swap_tab is an in-place remove+insert
        # so net index shift is zero; saved stays valid throughout.
        # After unblocking, one explicit setCurrentIndex replaces all the
        # competing QTimer.singleShot calls that previously raced each other.
        self._tabs.blockSignals(True)
        self._render_summary()
        self._render_watchlist()
        cur_name = self._tabs.tabText(saved)
        if cur_name == "Backtest":
            self._render_backtest()
            self._rendered_tabs.add("Backtest")
        elif cur_name in list(TICKERS) + self._custom:
            self._render_ticker(cur_name)
            self._rendered_tabs.add(cur_name)
        self._tabs.blockSignals(False)
        self._tabs.setCurrentIndex(saved)
        if self._computed:
            last    = next(iter(self._computed.values()))
            date_str = last.index[-1].strftime("%Y-%m-%d")
            iv = "Daily" if self._interval == "1d" else "Weekly"
            self._set_status(f"Updated  ·  {iv}  ·  last close {date_str}")
            self._add_btn.setEnabled(True)
            self._add_btn.setToolTip("")

    def _on_tab_changed(self, idx: int):
        name = self._tabs.tabText(idx)
        if name == "Backtest" and "Backtest" not in self._rendered_tabs and self._computed:
            self._tabs.blockSignals(True)
            try:
                self._render_backtest()
                self._rendered_tabs.add("Backtest")
            finally:
                self._tabs.blockSignals(False)
            QTimer.singleShot(0, lambda i=idx: self._tabs.setCurrentIndex(i))
        elif name in list(TICKERS) + self._custom and name not in self._rendered_tabs and self._computed:
            # Block signals so removeTab/insertTab in _swap_tab don't re-trigger this
            self._tabs.blockSignals(True)
            try:
                self._render_ticker(name)
                self._rendered_tabs.add(name)
            finally:
                self._tabs.blockSignals(False)
            # Restore focus to this tab after the swap settles
            QTimer.singleShot(0, lambda i=idx: self._tabs.setCurrentIndex(i))

    # ── Custom ticker ─────────────────────────────────────────────────────────

    def _prompt_add_ticker(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Ticker")
        dlg.setFixedWidth(340)
        dlg.setStyleSheet(
            f"QDialog{{background:{BG};border:1px solid #444;}}"
            f"QLabel{{color:{FG};background:transparent;}}"
            f"QLineEdit{{background:#2a2a2a;color:{FG};border:1px solid #555;"
            f"border-radius:4px;padding:4px 8px;font-size:10pt;}}"
            f"QLineEdit:focus{{border-color:#6666aa;}}"
            f"QPushButton{{background:#3a3a3a;color:{FG};border:1px solid #555;"
            f"border-radius:4px;padding:4px 14px;}}"
            f"QPushButton:hover{{background:#4a4a4a;}}"
            f"QPushButton:default{{background:#3a3a6a;border-color:#6666aa;}}"
        )
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(16, 16, 16, 12)
        vl.setSpacing(10)
        vl.addWidget(QLabel("Enter ticker symbol (e.g. AAPL, MSFT, GC=F):"))
        edit = QLineEdit()
        edit.setPlaceholderText("Ticker symbol…")
        vl.addWidget(edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vl.addWidget(btns)
        edit.setFocus()

        if dlg.exec() != QDialog.DialogCode.Accepted or not edit.text().strip():
            return
        sym = edit.text().strip().upper()
        self._set_status(f"Fetching {sym}…")
        self._run_worker(
            lambda: self._fetch_custom_worker(sym),
            on_done=lambda: self._open_custom_tab(sym, switch_tab=True),
        )

    def _add_from_watchlist(self, sym: str):
        self._set_status(f"Fetching {sym}…")
        self._run_worker(
            lambda: self._fetch_custom_worker(sym),
            on_done=lambda: self._open_custom_tab(sym, switch_tab=False),
        )

    def _fetch_custom_worker(self, sym: str):
        dd = Data.fetch_symbol(sym, "1d")
        dw = Data.fetch_symbol(sym, "1wk")
        if dd.empty:
            self._worker.status.emit(f"No data for '{sym}', check the symbol")
            return
        base = dd if self._interval == "1d" else (dw if not dw.empty else dd)
        comp = indicators.compute_all(base, dw if not dw.empty else dd)
        self._daily[sym]    = dd
        self._weekly[sym]   = dw
        self._computed[sym] = comp
        self._sig[sym]      = Sig.get_signals(comp)

    def _open_custom_tab(self, sym: str, switch_tab: bool = True):
        if sym not in self._sig:
            self._set_status(f"'{sym}' not found, check the symbol")
            return

        # Save current tab so _swap_tab calls don't leave us on the wrong tab
        restore_idx = self._tab_index(sym) if switch_tab else self._tabs.currentIndex()

        if sym not in self._custom:
            self._custom.append(sym)
            self._tabs.addTab(QWidget(), sym)

        self._render_ticker(sym)
        self._render_summary()
        if sym in self._sig:
            self._watchlist_sig[sym] = self._sig[sym]
        self._render_watchlist()

        # Defer so all Qt events from removeTab/insertTab settle first
        target = self._tab_index(sym) if switch_tab else restore_idx
        QTimer.singleShot(0, lambda i=target: self._tabs.setCurrentIndex(i))
        self._set_status(f"Added {sym}")

    # ── Summary tab ───────────────────────────────────────────────────────────

    def _render_summary(self):
        idx = self._tab_index("Summary")

        # Stop previous banner timer if any
        if hasattr(self, "_banner") and self._banner is not None:
            self._banner.stop()
            self._banner = None

        flow = _FlowGrid()
        flow.setStyleSheet(f"background:{BG};")

        def _score(name):
            s = self._sig.get(name)
            return int(s["score_str"]) if s else -999

        sorted_names = sorted(self._sig, key=_score, reverse=True)
        for name in sorted_names:
            s = self._sig.get(name)
            if s:
                flow.add_card(self._make_card(name, s, self._computed.get(name)))

        # Bullish banner items: main tickers + watchlist sorted by score desc
        all_sigs = {**self._watchlist_sig, **self._sig}  # sig wins on overlap
        bull_items = sorted(
            [
                (name, sig["score_str"])
                for name, sig in all_sigs.items()
                if sig.get("signal") == "BULL"
            ],
            key=lambda x: int(x[1]),
            reverse=True,
        )

        container = QWidget()
        container.setStyleSheet(f"background:{BG};")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        if bull_items:
            self._banner = _ScrollBanner(bull_items)
            vl.addWidget(self._banner)
        else:
            self._banner = None

        sa = self._scroll_wrap(flow)
        vl.addWidget(sa)

        self._swap_tab(idx, container, "Summary")

    # ── Info tab ──────────────────────────────────────────────────────────────

    def _build_info_tab(self):
        idx = self._tab_index("Info")

        content = QWidget()
        content.setStyleSheet(f"background:{BG};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(2)

        COL_W = [160, 240, 300, 300]
        SECTIONS = [
            ("MOMENTUM", [
                ("RSI", "Period: 14  ·  MA: SMA 14",
                 "Slope > 0 AND RSI > MA  (+10)\nRSI ≥ 56  (+10)",
                 "Slope ≤ 0 AND RSI < MA  (+10)\nRSI ≤ 36  (+10)"),
                ("Slow StochRSI", "K: 3  D: 3  Stoch: 14  RSI: 14", "K > D", "K ≤ D"),
                ("Fast StochRSI", "K: 3  D: 3  Stoch: 9   RSI: 6",  "K > D", "K ≤ D"),
            ]),
            ("TREND", [
                ("EMA  50/100/200", "Periods: 50, 100, 200",
                 "Price above ALL three EMAs", "Price below ALL three EMAs"),
                ("SMA  50/100/200", "Periods: 50, 100, 200",
                 "Price above ALL three SMAs", "Price below ALL three SMAs"),
            ]),
            ("STRUCTURE", [
                ("Bull Market Band", "20w SMA  ·  21w EMA",
                 "Price above both bands", "Price below both bands"),
                ("Ichimoku Cloud", "Conv: 9  Base: 26  SpanB: 52",
                 "Price above cloud top", "Price below cloud bottom"),
                ("Ichimoku Base", "Base Length: 26",
                 "Price above base line", "Price below base line"),
            ]),
            ("VOLUME", [
                ("Volume", "MA: 20  Trend: 5 bars",
                 "Vol above MA AND slope > 0", "Vol below MA AND slope ≤ 0"),
                ("OBV", "EMA: 20  Trend: 20 bars",
                 "OBV > EMA AND slope > 0", "OBV < EMA AND slope ≤ 0"),
                ("CNV", "SMA: 20",
                 "CNV > SMA", "CNV ≤ SMA"),
            ]),
            ("CHANNELS", [
                ("Keltner Channel", "EMA: 20  ATR: 10  Scalar: 2",
                 "Price > upper AND widening", "Price < lower AND widening"),
                ("NW Envelope", "BW: 8  Mult: 3  Lookback: 500",
                 "NW lower band inside Keltner", "NW upper band inside Keltner"),
            ]),
        ]

        # Header row
        hdr = QFrame()
        hdr.setStyleSheet("background:#2a2a2a;border-radius:4px;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(6, 4, 6, 4)
        for title, w in zip(["Indicator", "Parameters", "Bull", "Bear"], COL_W):
            l = _lbl(title, bold=True, size=8)
            l.setFixedWidth(w)
            hl.addWidget(l)
        hl.addStretch()
        layout.addWidget(hdr)

        for sec_name, rows in SECTIONS:
            sep = QLabel(f"  {sec_name}")
            sep.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            sep.setStyleSheet("color:#555;background:#1e1e1e;padding:4px 0;")
            layout.addWidget(sep)

            for i, (ind, params, bull, bear) in enumerate(rows):
                bg = "#242424" if i % 2 == 0 else "#202020"
                row_w = QFrame()
                row_w.setStyleSheet(f"background:{bg};")
                rl = QHBoxLayout(row_w)
                rl.setContentsMargins(6, 3, 6, 3)
                rl.setSpacing(0)
                for text, color, w in [
                    (ind,    FG,      COL_W[0]),
                    (params, FG_SUB,  COL_W[1]),
                    (bull,   BULL_FG, COL_W[2]),
                    (bear,   BEAR_FG, COL_W[3]),
                ]:
                    l = QLabel(text)
                    l.setFont(QFont("Segoe UI", 8))
                    l.setStyleSheet(f"color:{color};background:transparent;")
                    l.setFixedWidth(w)
                    l.setWordWrap(True)
                    rl.addWidget(l)
                rl.addStretch()
                layout.addWidget(row_w)

        # ── Signal Classification ──────────────────────────────────────────────
        sig_sep = QLabel("  SIGNAL CLASSIFICATION")
        sig_sep.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        sig_sep.setStyleSheet("color:#555;background:#1e1e1e;padding:4px 0;")
        layout.addWidget(sig_sep)

        SIG_COL_W  = [100, 380, 380]
        sig_hdr    = QFrame()
        sig_hdr.setStyleSheet("background:#2a2a2a;border-radius:4px;")
        sh = QHBoxLayout(sig_hdr)
        sh.setContentsMargins(6, 4, 6, 4)
        for title, w in zip(["Signal", "Entry condition", "Exits to Neutral when"], SIG_COL_W):
            l = _lbl(title, bold=True, size=8)
            l.setFixedWidth(w)
            sh.addWidget(l)
        sh.addStretch()
        layout.addWidget(sig_hdr)

        SIG_ROWS = [
            (
                "BULL", BULL_FG, BULL_BG,
                "Smoothed score crosses above +30  AND  5-bar slope is positive (score improving)",
                "Smoothed score retreats below +10",
            ),
            (
                "BEAR", BEAR_FG, BEAR_BG,
                "Smoothed score crosses below −30  AND  5-bar slope is negative (score deteriorating)",
                "Smoothed score recovers above −10",
            ),
            (
                "NEUTRAL", NEUT_FG, NEUT_BG,
                "Neither BULL nor BEAR entry condition is met",
                "N/A — default state",
            ),
        ]

        for i, (label, fg, bg, entry_txt, exit_txt) in enumerate(SIG_ROWS):
            row_bg = "#242424" if i % 2 == 0 else "#202020"
            rw = QFrame()
            rw.setStyleSheet(f"background:{row_bg};")
            rl = QHBoxLayout(rw)
            rl.setContentsMargins(6, 4, 6, 4)
            rl.setSpacing(0)

            sig_lbl = QLabel(label)
            sig_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            sig_lbl.setStyleSheet(
                f"color:{fg};background:{bg};border-radius:3px;"
                f"padding:1px 6px;"
            )
            sig_lbl.setFixedWidth(SIG_COL_W[0] - 8)
            sig_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(sig_lbl)
            rl.addSpacing(8)

            for text, w in [(entry_txt, SIG_COL_W[1]), (exit_txt, SIG_COL_W[2])]:
                l = QLabel(text)
                l.setFont(QFont("Segoe UI", 8))
                l.setStyleSheet(f"color:{FG};background:transparent;")
                l.setFixedWidth(w)
                l.setWordWrap(True)
                rl.addWidget(l)
            rl.addStretch()
            layout.addWidget(rw)

        layout.addStretch()
        self._swap_tab(idx, self._scroll_wrap(content), "Info")

    # ── Watchlist tab ─────────────────────────────────────────────────────────

    def _render_watchlist(self):
        idx    = self._tab_index("Watchlist")
        active = set(TICKERS.keys()) | set(TICKERS.values()) | set(self._custom)

        content = QWidget()
        content.setStyleSheet(f"background:{BG};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(2)

        def _score(sym):
            sig = self._watchlist_sig.get(sym)
            return int(sig["score_str"]) if sig else -999

        for category, entries in WATCHLIST.items():
            cat_lbl = _lbl(category.upper(), color=FG_SUB, size=8, bold=True)
            cat_lbl.setContentsMargins(0, 14, 0, 4)
            layout.addWidget(cat_lbl)

            for symbol, name in sorted(entries.items(), key=lambda x: _score(x[0]), reverse=True):
                is_added = symbol in active
                sig      = self._watchlist_sig.get(symbol)

                wrapper = QWidget()
                wrapper.setStyleSheet(f"background:{BG};")
                wl = QVBoxLayout(wrapper)
                wl.setContentsMargins(0, 0, 0, 0)
                wl.setSpacing(0)

                # ── Row ───────────────────────────────────────────────────────
                row = QFrame()
                row.setStyleSheet(f"QFrame{{background:{BG_CARD};border-radius:4px;}}")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(10, 5, 10, 5)
                rl.setSpacing(6)

                sym_lbl = _lbl(symbol, size=10, bold=True, mono=True)
                sym_lbl.setFixedWidth(90)
                rl.addWidget(sym_lbl)
                name_lbl = _lbl(name, color=FG_SUB)
                name_lbl.setFixedWidth(160)
                rl.addWidget(name_lbl)
                rl.addStretch()

                # Current / previous signal state (centered)
                row_sig_w = _build_signal_history_widget(self._watchlist_df.get(symbol), inline=True)
                if row_sig_w is not None:
                    rl.addWidget(row_sig_w)

                rl.addStretch()

                # Price + % change
                if sig:
                    close = sig["close"]
                    pct   = sig.get("pct_change", float("nan"))
                    if not math.isnan(close):
                        if close >= 1_000:
                            price_str = f"${close/1_000:.2f}k"
                        elif close >= 1:
                            price_str = f"${close:.2f}"
                        else:
                            price_str = f"${close:.4f}"
                        price_lbl = _lbl(price_str, color=FG, size=9, mono=True)
                        price_lbl.setFixedWidth(72)
                        price_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        rl.addWidget(price_lbl)
                    if not math.isnan(pct):
                        pct_color = BULL_FG if pct >= 0 else BEAR_FG
                        pct_str   = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"
                        pct_lbl   = _lbl(pct_str, color=pct_color, size=9, mono=True)
                        pct_lbl.setFixedWidth(64)
                        pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        rl.addWidget(pct_lbl)
                    rl.addSpacing(6)

                # Score badge
                if sig:
                    sbg, sfg = _sig_colors(sig["overall"])
                    sc = QLabel(sig["score_str"])
                    sc.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
                    sc.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    sc.setFixedSize(44, 22)
                    sc.setStyleSheet(
                        f"color:{sfg};background:{sbg};border-radius:3px;padding:0 4px;")
                    rl.addWidget(sc)
                else:
                    rl.addWidget(_lbl("—", color=FG_SUB, mono=True))

                # Add button
                ab = _btn("Added" if is_added else "＋ Add",
                          bg="#2a2a2a" if is_added else "#2d6a4f",
                          hover="#2a2a2a" if is_added else "#3a8a6a",
                          fg="#555" if is_added else FG,
                          w=76, h=24)
                ab.setEnabled(not is_added)
                if not is_added:
                    ab.clicked.connect(lambda _, s=symbol: self._add_from_watchlist(s))
                rl.addWidget(ab)

                # Details toggle
                if sig:
                    detail_panel = QWidget()
                    detail_panel.setStyleSheet(f"background:{BG};")
                    dp_layout = QVBoxLayout(detail_panel)
                    dp_layout.setContentsMargins(20, 4, 0, 4)
                    dp_layout.setSpacing(0)
                    detail_panel.setVisible(False)

                    db = _btn("▼", w=28, h=24)
                    rl.addWidget(db)

                    _open = [False]
                    def _make_toggle(sym=symbol, s=sig, dp=detail_panel,
                                     dpl=dp_layout, btn=db):
                        def _toggle():
                            if _open[0]:
                                dp.setVisible(False)
                                btn.setText("▼")
                                _open[0] = False
                            else:
                                while dpl.count():
                                    item = dpl.takeAt(0)
                                    if item.widget():
                                        item.widget().deleteLater()
                                dpl.addWidget(self._make_card(sym, s, self._watchlist_df.get(sym)))
                                dp.setVisible(True)
                                btn.setText("▲")
                                _open[0] = True
                        return _toggle

                    db.clicked.connect(_make_toggle())
                    wl.addWidget(row)
                    wl.addWidget(detail_panel)
                else:
                    wl.addWidget(row)

                layout.addWidget(wrapper)

        layout.addStretch()
        self._swap_tab(idx, self._scroll_wrap(content), "Watchlist")

    # ── Backtest tab ──────────────────────────────────────────────────────────

    def _render_backtest(self):
        idx = self._tab_index("Backtest")

        content = QWidget()
        content.setStyleSheet(f"background:{BG};")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(16, 10, 16, 10)
        vbox.setSpacing(8)

        # ── Controls ──────────────────────────────────────────────────────────
        ctrl = QFrame()
        ctrl.setStyleSheet(f"background:{BG_CARD};border-radius:6px;")
        ctrl.setFixedHeight(32)
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(8, 0, 8, 0)
        cl.setSpacing(4)

        def _arrow_btn(symbol):
            b = QPushButton(symbol)
            b.setFixedSize(20, 22)
            b.setFont(QFont("Segoe UI", 9))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setStyleSheet(
                f"QPushButton{{background:#3a3a3a;color:{FG};border:1px solid #555;"
                f"border-radius:3px;padding:0px;}}"
                f"QPushButton:hover{{background:#4a4a4a;}}"
            )
            return b

        def _spin(label, lo, hi, val, step=1):
            cl.addWidget(_lbl(label, color=FG_SUB, size=8))
            minus = _arrow_btn("▼")
            sb = QSpinBox()
            sb.setRange(lo, hi)
            sb.setValue(val)
            sb.setSingleStep(step)
            sb.setFixedSize(42, 22)
            sb.setStyleSheet(
                f"QSpinBox{{background:#2a2a2a;color:{FG};border:1px solid #555;"
                f"border-radius:3px;padding:1px 4px;}}"
                f"QSpinBox::up-button,QSpinBox::down-button{{width:0px;}}"
            )
            plus = _arrow_btn("▲")
            minus.clicked.connect(sb.stepDown)
            plus.clicked.connect(sb.stepUp)
            cl.addWidget(minus)
            cl.addWidget(sb)
            cl.addWidget(plus)
            cl.addSpacing(20)
            return sb

        # Ticker selector
        cl.addWidget(_lbl("Ticker", color=FG_SUB, size=8))
        ticker_cb = QComboBox()
        ticker_cb.addItems(list(TICKERS.keys()) + self._custom)
        ticker_cb.setFixedWidth(90)
        ticker_cb.setStyleSheet(
            f"QComboBox{{background:#2a2a2a;color:{FG};border:1px solid #555;"
            f"border-radius:4px;padding:2px 6px;}}"
            f"QComboBox::drop-down{{border:none;width:20px;}}"
            f"QComboBox QAbstractItemView{{background:#2a2a2a;color:{FG};"
            f"selection-background-color:#3a3a5a;}}"
        )
        cl.addWidget(ticker_cb)
        cl.addSpacing(8)

        entry_sb     = _spin("Entry",      10, 70, 30, 1)
        exit_sb      = _spin("Exit",        0, 40, 10, 1)
        slope_sb     = _spin("Slope bars",  2, 20,  5, 1)

        reset_btn = _btn("Reset", h=22)
        reset_btn.setFixedHeight(22)
        def _reset():
            for sb, v in [(entry_sb, 30), (exit_sb, 10), (slope_sb, 5)]:
                sb.blockSignals(True)
                sb.setValue(v)
                sb.blockSignals(False)
            _run()
        reset_btn.clicked.connect(_reset)
        cl.addWidget(reset_btn)

        cl.addStretch()
        vbox.addWidget(ctrl)

        # ── Chart ─────────────────────────────────────────────────────────────
        from matplotlib.figure import Figure
        fig = Figure(figsize=(12, 5), facecolor=BG)
        canvas = FigureCanvasQTAgg(fig)
        canvas.setStyleSheet(f"background:{BG};")
        vbox.addWidget(canvas)

        C = __import__("config").C

        def _run(*_):
            ticker    = ticker_cb.currentText()
            entry_val = entry_sb.value()
            exit_val  = exit_sb.value()
            slope_val = slope_sb.value()

            df = self._computed.get(ticker)
            if df is None or df.empty:
                return

            res = BT.run_backtest(df, entry=entry_val, exit_th=exit_val,
                                   slope_bars=slope_val,
                                   hold_through_neutral=True)
            if not res:
                return

            # Draw chart
            fig.clear()
            ax1 = fig.add_subplot(2, 1, 1)   # price + trade markers
            ax2 = fig.add_subplot(2, 1, 2, sharex=ax1)   # score / states

            for ax in [ax1, ax2]:
                ax.set_facecolor(BG_CARD)
                ax.tick_params(colors="#666", labelsize=7)
                for spine in ax.spines.values():
                    spine.set_edgecolor("#333")

            dates  = res["closes"].index
            closes = res["closes"].values

            # Panel 1: price
            ax1.plot(dates, closes, color=C["price"], lw=0.9, zorder=2)
            ax1.set_ylabel("Price", color=FG_SUB, fontsize=7)

            # Shade BULL/BEAR regions
            states = res["states"]
            for i in range(1, len(states)):
                if states.iloc[i] == "BULL":
                    ax1.axvspan(dates[i-1], dates[i], color=BULL_BG, alpha=0.4, lw=0)
                elif states.iloc[i] == "BEAR":
                    ax1.axvspan(dates[i-1], dates[i], color=BEAR_BG, alpha=0.4, lw=0)

            # Trade entry/exit markers (skip exit arrow for still-open trades)
            for t in res["trades"]:
                ax1.plot(t["entry_date"], t["entry_price"],
                         marker="^", color=BULL_FG, ms=6, zorder=5)
                if not t["open"]:
                    ax1.plot(t["exit_date"], t["exit_price"],
                             marker="v", color=BEAR_FG, ms=6, zorder=5)

            # Panel 2: score with state coloring
            raw_score = Sig.score_history(df, n=len(df))
            score_dates = raw_score.index
            score_vals  = raw_score.values
            ax2.plot(score_dates, score_vals, color="#888", lw=0.8)
            ax2.axhline(entry_val,  color=BULL_FG, lw=0.6, linestyle="--", alpha=0.5)
            ax2.axhline(-entry_val, color=BEAR_FG, lw=0.6, linestyle="--", alpha=0.5)
            ax2.axhline(exit_val,   color=BULL_FG, lw=0.4, linestyle=":",  alpha=0.4)
            ax2.axhline(-exit_val,  color=BEAR_FG, lw=0.4, linestyle=":",  alpha=0.4)
            ax2.axhline(0, color="#444", lw=0.6)
            ax2.set_ylabel("Score", color=FG_SUB, fontsize=7)

            fig.tight_layout(pad=1.0)
            canvas.draw()

            # ── Crosshairs ────────────────────────────────────────────────────
            ch = dict(color="#555", lw=0.7, linestyle="--")
            v1 = ax1.axvline(x=dates[0], visible=False, **ch)
            v2 = ax2.axvline(x=dates[0], visible=False, **ch)
            h1 = ax1.axhline(y=closes[0], visible=False, **ch)
            h2 = ax2.axhline(y=score_vals[0], visible=False, **ch)

            def _on_move(event):
                for ln in (v1, v2, h1, h2):
                    ln.set_visible(False)
                if event.inaxes in (ax1, ax2) and event.xdata is not None:
                    v1.set_xdata([event.xdata, event.xdata]); v1.set_visible(True)
                    v2.set_xdata([event.xdata, event.xdata]); v2.set_visible(True)
                    if event.inaxes is ax1:
                        h1.set_ydata([event.ydata, event.ydata]); h1.set_visible(True)
                    else:
                        h2.set_ydata([event.ydata, event.ydata]); h2.set_visible(True)
                canvas.draw_idle()

            if hasattr(canvas, '_ch_cid'):
                canvas.mpl_disconnect(canvas._ch_cid)
            canvas._ch_cid = canvas.mpl_connect("motion_notify_event", _on_move)

        # Wire controls
        ticker_cb.currentIndexChanged.connect(_run)
        entry_sb.valueChanged.connect(_run)
        exit_sb.valueChanged.connect(_run)
        slope_sb.valueChanged.connect(_run)

        self._swap_tab(idx, content, "Backtest")
        _run()

    # ── Card ──────────────────────────────────────────────────────────────────

    def _make_card(self, name: str, s: dict, df=None) -> QFrame:
        overall = s["overall"]
        close   = s["close"]
        if close >= 1_000:
            close_str = f"${close/1_000:.2f}k"
        elif close >= 1:
            close_str = f"${close:.2f}"
        else:
            close_str = f"${close:.4f}"
        hdr_bg, hdr_fg = _sig_colors(overall)
        ovr_txt = "BULL" if overall is True else "BEAR" if overall is False else ""

        # % change from previous close
        pct_str = ""
        pct_color = hdr_fg
        if df is not None and not df.empty:
            closes = df["Close"].dropna().values
            if len(closes) >= 2:
                pct = (closes[-1] / closes[-2] - 1) * 100
                pct_str  = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
                pct_color = BULL_FG if pct >= 0 else BEAR_FG

        card = QFrame()
        card.setFixedWidth(CARD_W)
        card.setStyleSheet(
            "QFrame{background:#242424;border:1px solid #333;border-radius:8px;}")
        card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        def _nav(_, n=name):
            i = self._tab_index(n)
            if i >= 0:
                self._tabs.setCurrentIndex(i)
        card.mousePressEvent = _nav

        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 6)
        cl.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet(
            f"QFrame{{background:{hdr_bg};border-radius:7px 7px 0 0;}}")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(10, 7, 10, 7)
        hl.addWidget(_lbl(name, color=hdr_fg, size=12, bold=True))
        hl.addStretch()
        if pct_str:
            hl.addWidget(_lbl(pct_str, color=pct_color, size=8, mono=True))
            hl.addSpacing(6)
        hl.addWidget(_lbl(close_str, color=hdr_fg, size=9, mono=True))
        hl.addSpacing(8)
        score_label_text = f"{ovr_txt}  {s['score_str']}" if ovr_txt else s['score_str']
        score_lbl = _lbl(score_label_text, color=hdr_fg, size=8, bold=True)
        score_lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        hl.addWidget(score_lbl)
        cl.addWidget(hdr)

        # Score sparkline
        if df is not None and not df.empty:
            hist = Sig.score_history(df, n=60)
            if len(hist) >= 10:
                spark = _ScoreSparkline(hist.tolist())
                spark.setStyleSheet("background:#1e1e1e;")
                cl.addWidget(spark)

        # Current / previous signal state
        sig_hist_w = _build_signal_history_widget(df)
        if sig_hist_w is not None:
            cl.addWidget(_hsep())
            cl.addWidget(sig_hist_w)

        # Section separator + label
        def _section(title):
            cl.addWidget(_hsep())
            sep_lbl = QLabel(f"  {title}")
            sep_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            sep_lbl.setStyleSheet("color:#555;background:#1a1a1a;padding:3px 0;")
            cl.addWidget(sep_lbl)

        # Indicator row
        def _score_badge(score_str: str, bull) -> QLabel | None:
            if not score_str:
                return None
            fg = BULL_FG if bull is True else BEAR_FG if bull is False else "#aaaaaa"
            bg = "#1a2e1a" if bull is True else "#2e1a1a" if bull is False else "#2a2614"
            lbl = QLabel(score_str)
            lbl.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(30, 16)
            lbl.setStyleSheet(f"color:{fg};background:{bg};border-radius:3px;")
            return lbl

        def _row(label, value, bull=None, score=""):
            val_fg = (BULL_FG if bull is True else
                      BEAR_FG if bull is False else "#aaaaaa")
            r = QWidget()
            r.setStyleSheet("background:#242424;")
            rl = QHBoxLayout(r)
            rl.setContentsMargins(8, 1, 8, 1)
            rl.setSpacing(4)
            lw = _lbl(label, color="#666", size=8)
            lw.setFixedWidth(98)
            rl.addWidget(lw)
            rl.addWidget(_lbl(value, color=val_fg, size=8, mono=True))
            rl.addStretch()
            badge = _score_badge(score, bull)
            if badge:
                rl.addWidget(badge)
            cl.addWidget(r)

        # MA row (coloured per period, single combined score badge)
        def _ma_row(label, ma_dict):
            r = QWidget()
            r.setStyleSheet("background:#242424;")
            rl = QHBoxLayout(r)
            rl.setContentsMargins(8, 1, 8, 1)
            rl.setSpacing(4)
            lw = _lbl(label, color="#666", size=8)
            lw.setFixedWidth(98)
            rl.addWidget(lw)
            for p in MA_PERIODS:
                above = ma_dict[p]["above"]
                fg    = BULL_FG if above else (BEAR_FG if above is False else "#aaa")
                arrow = "↑" if above else ("↓" if above is False else "?")
                rl.addWidget(_lbl(f"{p}{arrow}", color=fg, size=8, mono=True))
            rl.addStretch()
            # Sum all score contributions into one badge
            total = 0
            for key in ("score50", "score200"):
                sc = ma_dict.get(key, "")
                if sc:
                    total += int(sc)
            if total != 0:
                sc_str = f"+{total}" if total > 0 else str(total)
                badge  = _score_badge(sc_str, total > 0)
                if badge:
                    rl.addWidget(badge)
            cl.addWidget(r)

        ichi = s["Ichimoku"]
        srsi = s["StochRSI"]
        cfg0, cfg1 = STOCHRSI_CONFIGS[0]["label"], STOCHRSI_CONFIGS[1]["label"]

        _section("MOMENTUM")
        rsi_score = s["RSI"].get("score", "")
        rsi_col   = True if rsi_score.startswith("+") else (False if rsi_score.startswith("-") else None)
        _row("RSI",           s["RSI"]["text"],       rsi_col,                 rsi_score)
        _row("Slow StochRSI", srsi[cfg0]["text"],     srsi[cfg0]["bull"])
        _row("Fast StochRSI", srsi[cfg1]["text"],     srsi[cfg1]["bull"])

        _section("TREND")
        _ma_row("EMA", s["EMA"])
        _ma_row("SMA", s["SMA"])

        _section("STRUCTURE")
        _row("Ichi Cloud",    ichi["cloud_text"],    ichi["cloud_bull"],  ichi.get("cloud_score", ""))
        _row("Ichi Base",     ichi["base_text"],     ichi["base_bull"],   ichi.get("base_score", ""))
        _row("Bull Band",     s["BullBand"]["text"], s["BullBand"]["bull"])

        _section("VOLUME")
        _row("Volume",        s["Volume"]["text"],   s["Volume"]["bull"])
        _row("OBV",           s["OBV"]["text"],      s["OBV"]["bull"],    s["OBV"].get("score", ""))
        _row("CNV",           s["CNV"]["text"],      s["CNV"]["bull"],    s["CNV"].get("score", ""))

        _section("CHANNELS")
        _row("Keltner",       s["Keltner"]["text"],  s["Keltner"]["bull"], s["Keltner"].get("score", ""))
        _row("NW Envelope",   s["NW"]["text"],       s["NW"]["bull"])

        return card

    # ── Ticker chart tabs ──────────────────────────────────────────────────────

    def _render_ticker(self, name: str):
        idx = self._tab_index(name)
        if idx < 0:
            return

        df = self._computed.get(name)
        container = QWidget()
        container.setStyleSheet("background:#1e1e1e;")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        if df is None or df.empty:
            vl.addWidget(_lbl(f"No data for {name}", color=FG_SUB))
            self._swap_tab(idx, container, name)
            return

        n_bars = LOOKBACK_OPTIONS[self._lookback][self._interval]

        # Nested tab widget: one sub-tab per indicator
        inner = QTabWidget()
        inner.setStyleSheet(f"""
            QTabWidget::pane  {{ background:#1e1e1e; border:none; }}
            QTabBar::tab      {{ background:#242424; color:#888; padding:5px 14px;
                                 border:none; border-bottom:2px solid transparent;
                                 font-family:'Segoe UI'; font-size:8pt; }}
            QTabBar::tab:selected {{ color:#e0e0e0; background:#2e2e2e;
                                     border-bottom:2px solid #6060a0; }}
            QTabBar::tab:hover    {{ background:#2e2e2e; color:#ccc; }}
        """)

        tb_style = (
            "background:#242424;color:#888;border:none;"
            "QToolButton{background:#2a2a2a;border:none;border-radius:3px;}"
            "QToolButton:hover{background:#3a3a3a;}"
        )

        for label, fig_fn in [
            ("Volume",   Charts.make_volume_figure),
            ("Score",    Charts.make_score_figure),
            ("RSI",      Charts.make_rsi_figure),
            ("Stoch RSI", Charts.make_stoch_figure),
            ("OBV",      Charts.make_obv_figure),
            ("Keltner", Charts.make_kc_cnv_figure),
        ]:
            fig    = fig_fn(name, df, self._interval, n_bars)
            canvas = FigureCanvasQTAgg(fig)
            _attach_crosshair(canvas)
            tb     = NavigationToolbar2QT(canvas)
            tb.setStyleSheet(tb_style)
            page = QWidget()
            pl   = QVBoxLayout(page)
            pl.setContentsMargins(0, 0, 0, 0)
            pl.setSpacing(0)
            pl.addWidget(tb)
            pl.addWidget(canvas)
            inner.addTab(page, label)

        vl.addWidget(inner)
        self._swap_tab(idx, container, name)

