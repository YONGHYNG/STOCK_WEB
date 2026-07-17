# 역할: 데스크톱 매매 화면과 사용자 조작을 담당하는 파일.
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, QTimer, Signal, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from PySide6.QtCore import QDate

from concurrent.futures import Future

from backend.strategy.multi_timeframe_strategy import TradingAIEngine
from backend.strategy.backtester import Backtester, BacktestConfig
from backend.bitget.market_api import BitgetClient
from backend.bitget.client import BitgetPrivateClient
import backend.credentials as creds_store
from backend.order.paper_trader import PaperTrader
from backend.risk.risk_manager import RiskManager
from backend.power_keepawake import keep_awake
import backend.risk.settings as risk_settings_store
from backend.trading_modes import TradingMode
from backend.config import (
    DEFAULT_TIMEFRAME,
    INITIAL_CANDLE_LIMIT,
    RECENT_CANDLE_LIMIT_BY_TIMEFRAME,
    REFRESH_INTERVAL_MS,
    REFRESH_CANDLE_LIMIT,
    SYMBOL,
    TIMEFRAMES,
    USE_DEMO_DATA,
)
from backend.database import (
    close_trade,
    get_all_time_high,
    get_all_time_low,
    get_open_trade,
    get_recent_candles,
    get_recent_trades,
    insert_candles,
    insert_signal,
    open_trade,
    purge_unaligned_candles,
)

# ── Design tokens ──────────────────────────────────────────────────────────────
BG       = "#0d1117"
PANEL    = "#161b22"
CARD     = "#1c2128"
BORDER   = "#30363d"
TEXT     = "#e6edf3"
TEXT2    = "#7d8590"
GREEN    = "#3fb950"
GREEN_DIM= "#0d2818"
RED      = "#f85149"
RED_DIM  = "#2d0f0d"
YELLOW   = "#e3b341"
YELLOW_DIM="#2d2009"
BLUE     = "#58a6ff"
BLUE_DIM = "#0d1f33"
PURPLE   = "#bc8cff"

SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

DIR_COLOR = {"LONG": GREEN,  "SHORT": RED,   "HOLD": YELLOW}
DIR_BG    = {"LONG": GREEN_DIM, "SHORT": RED_DIM, "HOLD": YELLOW_DIM}
DIR_ARROW = {"LONG": "▲",   "SHORT": "▼",   "HOLD": "◆"}


# ── Reusable widgets ───────────────────────────────────────────────────────────

class Divider(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("divider")
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)


class SectionHeader(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("sectionHeader")


class RiskCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("riskCard")
        lbl = QLabel(title)
        lbl.setObjectName("riskTitle")
        self.val = QLabel("—")
        self.val.setObjectName("riskValue")
        self.val.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(5)
        lay.addWidget(lbl)
        lay.addWidget(self.val)

    def update(self, text: str, color: str = TEXT):
        self.val.setText(text)
        self.val.setStyleSheet(f"color: {color};")


class TimeframeCell(QFrame):
    def __init__(self, tf: str):
        super().__init__()
        self.setObjectName("tfCell")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._tf_lbl = QLabel(tf)
        self._tf_lbl.setObjectName("tfName")
        self._dir_lbl = QLabel("—")
        self._dir_lbl.setObjectName("tfDir")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(3)
        lay.addWidget(self._tf_lbl)
        lay.addWidget(self._dir_lbl)

    def set_direction(self, direction: str):
        color = DIR_COLOR.get(direction, TEXT2)
        arrow = DIR_ARROW.get(direction, "—")
        self._dir_lbl.setText(f"{arrow}  {direction}")
        self._dir_lbl.setStyleSheet(f"color: {color}; font-weight: 800;")


class ScoreBar(QWidget):
    def __init__(self, label: str, bar_id: str):
        super().__init__()
        self._lbl = QLabel(label)
        self._lbl.setObjectName("barLabel")
        self._lbl.setFixedWidth(108)
        self._bar = QProgressBar()
        self._bar.setObjectName(bar_id)
        self._bar.setRange(0, 100)
        self._bar.setValue(50)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(14)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self._lbl)
        row.addWidget(self._bar)

    def update(self, label: str, value: int):
        self._lbl.setText(label)
        self._bar.setValue(max(0, min(100, value)))


# ── API 설정 다이얼로그 ────────────────────────────────────────────────────────

class CredentialsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bitget API 연동 설정")
        self.setMinimumWidth(420)
        self.setModal(True)

        creds = creds_store.load()

        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 10)

        self._key   = QLineEdit(creds.api_key)
        self._secret= QLineEdit(creds.secret_key)
        self._pass  = QLineEdit(creds.passphrase)

        self._secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass.setEchoMode(QLineEdit.EchoMode.Password)

        self._key.setPlaceholderText("API Key")
        self._secret.setPlaceholderText("Secret Key")
        self._pass.setPlaceholderText("Passphrase")

        form.addRow("API Key",     self._key)
        form.addRow("Secret Key",  self._secret)
        form.addRow("Passphrase",  self._pass)

        notice = QLabel(
            "⚠ 실제 주문이 발생합니다. 읽기 전용(Read) 권한만 있는 API 키로 테스트 후 사용하세요.\n"
            "자격증명은 data/credentials.json에 로컬 저장됩니다."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(f"color: {YELLOW}; font-size: 11px; padding: 8px 0;")

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(notice)
        layout.addWidget(btns)

        self.setStyleSheet(f"""
            QDialog {{ background: {PANEL}; color: {TEXT}; }}
            QLabel  {{ color: {TEXT}; }}
            QLineEdit {{
                background: {CARD}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 5px;
                padding: 6px 10px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {BLUE}; }}
            QDialogButtonBox QPushButton {{
                background: {CARD}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 5px;
                padding: 6px 18px; font-weight: 700;
            }}
            QDialogButtonBox QPushButton:hover {{ border-color: {BLUE}; color: {BLUE}; }}
        """)

    def _save(self):
        creds_store.save(
            self._key.text().strip(),
            self._secret.text().strip(),
            self._pass.text().strip(),
        )
        self.accept()


# ── Signals ────────────────────────────────────────────────────────────────────

class WorkerSignals(QObject):
    completed       = Signal(object, object, object)
    failed          = Signal(str)
    progress        = Signal(str)
    price_updated   = Signal(float)
    account_updated = Signal(object, object)   # (account_dict, positions_list)


# ── Main window ────────────────────────────────────────────────────────────────

class TradingMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BTCUSDT · Multi-Timeframe Signal Dashboard")
        self.resize(1200, 860)
        self.setMinimumSize(960, 700)

        self.clients = {tf: BitgetClient(timeframe=tf, demo_mode=USE_DEMO_DATA) for tf in TIMEFRAMES}
        self.engine  = TradingAIEngine()

        # 인증 클라이언트 (자격증명 로드)
        self._creds         = creds_store.load()
        self._private_client: BitgetPrivateClient | None = self._make_private_client()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._future   = None
        self._seeded   = False

        self._signals = WorkerSignals()
        self._signals.completed.connect(self._on_done)
        self._signals.failed.connect(self._on_failed)
        self._signals.progress.connect(self._log)
        self._signals.price_updated.connect(self._on_price_update)
        self._signals.account_updated.connect(self._on_account_update)

        # 가격 전용 executor
        self._price_executor = ThreadPoolExecutor(max_workers=1)
        self._price_future: Future | None = None
        self._last_price: float | None = None

        # 계정 전용 executor
        self._account_executor = ThreadPoolExecutor(max_workers=1)
        self._account_future: Future | None = None

        self._spin_idx = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spinner)

        self._tf_cells: dict[str, TimeframeCell] = {}
        self._risk_cards: dict[str, RiskCard] = {}

        # 트레이드 추적
        self._open_trade_id: int | None = None
        self._open_trade_data: dict | None = None   # {direction, entry, sl, tp1, tp2}

        # 자동매매 / 리스크 / 모의매매
        self._auto_trade_enabled = False
        self._cached_account: dict | None = None
        self._cached_positions: list = []
        self._pending_live_order_id: str | None = None
        self._trading_mode = TradingMode.SIGNAL_ONLY
        self._risk_cfg  = risk_settings_store.load()
        self._auto_threshold = self._risk_cfg.confidence_threshold
        self._risk_mgr  = RiskManager(self._risk_cfg)
        self._paper_trader = PaperTrader()

        # 앱 재시작 시 기존 오픈 거래 복구 (LIVE)
        existing = get_open_trade(SYMBOL, trade_type="LIVE")
        if existing:
            self._open_trade_id = existing["id"]
            self._open_trade_data = {
                "direction": existing["direction"],
                "entry":     existing["entry_price"],
                "sl":        existing["stop_loss"],
                "tp1":       existing["take_profit_1"],
                "tp2":       existing["take_profit_2"],
            }
        # 모의매매 복구
        self._paper_trader.restore_from_db()

        self._build_ui()

        # 시작 시 기존 복기 데이터 로드
        self._refresh_trade_table()

        # 전체 분석 주기 (15초)
        self._poll = QTimer(self)
        self._poll.timeout.connect(self.refresh)
        self._poll.start(REFRESH_INTERVAL_MS)
        QTimer.singleShot(0, self.refresh)

        # 가격 실시간 갱신 (2초)
        self._price_timer = QTimer(self)
        self._price_timer.timeout.connect(self._fetch_price)
        self._price_timer.start(2000)

        # 계정 정보 갱신 (10초)
        self._account_timer = QTimer(self)
        self._account_timer.timeout.connect(self._fetch_account)
        if self._private_client:
            self._account_timer.start(10000)
            QTimer.singleShot(500, self._fetch_account)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        main = QVBoxLayout(root)
        main.setContentsMargins(22, 16, 22, 20)
        main.setSpacing(10)

        # Header
        main.addLayout(self._make_header())
        main.addWidget(Divider())

        # Hero: price + direction + strategy state
        main.addLayout(self._make_hero())
        main.addWidget(Divider())

        # Strategy context bars
        main.addWidget(SectionHeader("STRATEGY CONTEXT"))
        self._long_bar  = ScoreBar("RSI14       —", "longBar")
        self._short_bar = ScoreBar("VOLUME      —", "shortBar")
        main.addWidget(self._long_bar)
        main.addWidget(self._short_bar)
        main.addWidget(Divider())

        # Risk management row
        main.addWidget(SectionHeader("RISK MANAGEMENT"))
        main.addLayout(self._make_risk_row())
        main.addWidget(Divider())

        # 계정 패널
        main.addWidget(SectionHeader("BITGET ACCOUNT"))
        main.addLayout(self._make_account_panel())
        main.addWidget(Divider())

        # Timeframe grid
        main.addWidget(SectionHeader("TIMEFRAME BREAKDOWN"))
        main.addLayout(self._make_tf_grid())
        main.addWidget(Divider())

        # 탭: AI 로그 / 투자 복기 / 리스크 설정 / 백테스트
        self._tabs = QTabWidget()
        self._tabs.setObjectName("bottomTabs")
        self._tabs.setMinimumHeight(220)

        # Tab 1: AI Log
        self._log_view = QTextEdit()
        self._log_view.setObjectName("logView")
        self._log_view.setReadOnly(True)
        self._tabs.addTab(self._log_view, "  AI 분석 로그  ")

        # Tab 2: Trade History
        self._trade_table = self._make_trade_table()
        self._tabs.addTab(self._trade_table, "  투자 복기  ")

        # Tab 3: Risk Settings
        self._tabs.addTab(self._make_risk_tab(), "  리스크 설정  ")

        # Tab 4: Backtest
        self._tabs.addTab(self._make_backtest_tab(), "  백테스트  ")

        main.addWidget(self._tabs, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(self._css())

    def _make_header(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(12)

        brand = QVBoxLayout()
        brand.setSpacing(2)
        sym = QLabel("₿  BTCUSDT PERPETUAL")
        sym.setObjectName("symbol")
        sub = QLabel("Bitget Futures  ·  Multi-Timeframe Signal Monitor")
        sub.setObjectName("symSub")
        brand.addWidget(sym)
        brand.addWidget(sub)

        self._status_lbl = QLabel("● LIVE" if not USE_DEMO_DATA else "● DEMO")
        self._status_lbl.setObjectName("statusLive" if not USE_DEMO_DATA else "statusDemo")

        self._updated_lbl = QLabel("Updated: —")
        self._updated_lbl.setObjectName("updated")

        self._refresh_btn = QPushButton("⟳  Refresh")
        self._refresh_btn.setObjectName("refreshBtn")
        self._refresh_btn.setFixedWidth(110)
        self._refresh_btn.clicked.connect(self.refresh)

        self._settings_btn = QPushButton("⚙  API 연동")
        self._settings_btn.setObjectName("settingsBtn")
        self._settings_btn.setFixedWidth(110)
        self._settings_btn.clicked.connect(self._open_settings)

        # 모드 선택 콤보박스
        self._mode_combo = QComboBox()
        self._mode_combo.setObjectName("modeCombo")
        for mode in TradingMode:
            self._mode_combo.addItem(mode.label(), mode.value)  # 문자열로 저장
        self._mode_combo.setCurrentIndex(0)   # SIGNAL_ONLY
        self._mode_combo.setFixedWidth(120)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        # 긴급정지 버튼
        self._emergency_btn = QPushButton("⛔  긴급정지")
        self._emergency_btn.setObjectName("emergencyBtn")
        self._emergency_btn.setFixedWidth(110)
        self._emergency_btn.clicked.connect(self._emergency_stop)

        lay.addLayout(brand, 1)
        lay.addWidget(self._updated_lbl)
        lay.addWidget(self._status_lbl)
        lay.addWidget(self._mode_combo)
        lay.addWidget(self._refresh_btn)
        lay.addWidget(self._settings_btn)
        lay.addWidget(self._emergency_btn)
        return lay

    def _make_hero(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(24)

        # Price
        price_col = QVBoxLayout()
        price_col.setSpacing(4)
        price_col.addWidget(SectionHeader("CURRENT PRICE"))
        self._price_lbl = QLabel("—")
        self._price_lbl.setObjectName("priceHero")
        price_col.addWidget(self._price_lbl)

        # Direction badge
        dir_col = QVBoxLayout()
        dir_col.setSpacing(4)
        dir_col.addWidget(SectionHeader("SIGNAL"))
        self._dir_badge = QLabel("—")
        self._dir_badge.setObjectName("dirBadge")
        self._dir_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dir_badge.setMinimumSize(190, 52)
        dir_col.addWidget(self._dir_badge)

        # Strategy signal
        conf_col = QVBoxLayout()
        conf_col.setSpacing(4)
        conf_col.addWidget(SectionHeader("STRATEGY"))
        self._conf_lbl = QLabel("—")
        self._conf_lbl.setObjectName("confLbl")
        self._conf_lbl.setMinimumWidth(260)
        self._conf_lbl.setWordWrap(True)
        conf_col.addWidget(self._conf_lbl)

        # Wait state / levels
        mode_col = QVBoxLayout()
        mode_col.setSpacing(4)
        mode_col.addWidget(SectionHeader("WAIT / LEVELS"))
        self._ath_lbl = QLabel("State: HOLD")
        self._ath_lbl.setObjectName("modeLbl")
        self._ath_lbl.setMinimumWidth(220)
        self._ath_lbl.setWordWrap(True)
        self._atl_lbl = QLabel("Level: —")
        self._atl_lbl.setObjectName("modeLbl")
        self._atl_lbl.setMinimumWidth(220)
        self._atl_lbl.setWordWrap(True)
        mode_col.addWidget(self._ath_lbl)
        mode_col.addWidget(self._atl_lbl)

        lay.addLayout(price_col, 2)
        lay.addLayout(dir_col, 1)
        lay.addLayout(conf_col, 1)
        lay.addLayout(mode_col, 1)
        return lay

    def _make_risk_row(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(8)
        specs = [
            ("entry", "진입가"),
            ("stop",  "손절가"),
            ("tp1",   "1차 익절가"),
            ("tp2",   "2차 익절가"),
            ("rr",    "손익비"),
        ]
        for key, title in specs:
            card = RiskCard(title)
            self._risk_cards[key] = card
            lay.addWidget(card)
        return lay

    def _make_risk_tab(self) -> QWidget:
        """리스크 설정 탭 위젯을 생성합니다."""
        w = QWidget()
        w.setObjectName("tabPage")
        root = QVBoxLayout(w)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        s = self._risk_cfg

        def spin(lo, hi, dec, val, step=None) -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setObjectName("acctSpin")
            sb.setRange(lo, hi)
            sb.setDecimals(dec)
            sb.setValue(val)
            if step:
                sb.setSingleStep(step)
            sb.setFixedWidth(120)
            return sb

        def ispin(lo, hi, val) -> QSpinBox:
            sb = QSpinBox()
            sb.setObjectName("acctSpin")
            sb.setRange(lo, hi)
            sb.setValue(val)
            sb.setFixedWidth(120)
            return sb

        form = QFormLayout()
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        self._rs_order_size   = spin(0.001, 10.0,   3, s.order_size_btc,    0.001)
        self._rs_max_loss     = spin(0.1,   50.0,   1, s.max_loss_pct,      0.5)
        self._rs_daily_loss   = spin(0.1,   100.0,  1, s.daily_max_loss_pct,1.0)
        self._rs_consec_loss  = ispin(1, 20, s.consecutive_loss_limit)
        self._rs_confidence   = spin(0.0, 99.0,     0, s.confidence_threshold, 5.0)
        self._rs_reentry_wait = ispin(0, 3600, s.reentry_wait_seconds)
        self._rs_max_lev      = ispin(1, 125, s.max_leverage)
        self._rs_live_allow   = QCheckBox("실거래 주문 허용  (반드시 이해 후 체크)")
        self._rs_live_allow.setObjectName("autoChk")
        self._rs_live_allow.setChecked(s.live_trading_allowed)

        form.addRow("1회 주문 수량 (BTC):",  self._rs_order_size)
        form.addRow("1회 최대 손실률 (%):",   self._rs_max_loss)
        form.addRow("일일 최대 손실률 (%):",  self._rs_daily_loss)
        form.addRow("연속 손실 정지 횟수:",    self._rs_consec_loss)
        form.addRow("확정 신호 기준 (%):", self._rs_confidence)
        form.addRow("재진입 대기 시간 (초):",  self._rs_reentry_wait)
        form.addRow("최대 레버리지:",          self._rs_max_lev)
        form.addRow("",                        self._rs_live_allow)

        # 저장 버튼
        save_btn = QPushButton("설정 저장")
        save_btn.setObjectName("settingsBtn")
        save_btn.setFixedWidth(120)
        save_btn.clicked.connect(self._save_risk_settings)

        root.addLayout(form)
        root.addWidget(save_btn)
        root.addStretch()
        return w

    def _save_risk_settings(self):
        from backend.risk.settings import RiskSettings
        s = RiskSettings(
            order_size_btc         = self._rs_order_size.value(),
            max_loss_pct           = self._rs_max_loss.value(),
            daily_max_loss_pct     = self._rs_daily_loss.value(),
            consecutive_loss_limit = self._rs_consec_loss.value(),
            confidence_threshold   = self._rs_confidence.value(),
            reentry_wait_seconds   = self._rs_reentry_wait.value(),
            max_leverage           = self._rs_max_lev.value(),
            live_trading_allowed   = self._rs_live_allow.isChecked(),
        )
        risk_settings_store.save(s)
        self._risk_cfg = s
        self._risk_mgr = RiskManager(s)
        self._auto_threshold = s.confidence_threshold
        if hasattr(self, "_auto_spin"):
            self._auto_spin.blockSignals(True)
            self._auto_spin.setValue(s.confidence_threshold)
            self._auto_spin.blockSignals(False)
        if hasattr(self, "_size_spin"):
            self._size_spin.setValue(s.order_size_btc)
        self._log(f"[리스크 설정] 저장 완료  실거래허용={s.live_trading_allowed}")

    def _make_backtest_tab(self) -> QWidget:
        """백테스트 탭 위젯을 생성합니다."""
        w = QWidget()
        w.setObjectName("tabPage")
        root = QVBoxLayout(w)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # 설정 행
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(12)

        def date_edit(default_days_ago=0) -> QDateEdit:
            de = QDateEdit()
            de.setObjectName("acctSpin")
            de.setCalendarPopup(True)
            de.setDisplayFormat("yyyy-MM-dd")
            d = QDate.currentDate().addDays(-default_days_ago)
            de.setDate(d)
            de.setFixedWidth(130)
            return de

        def dspin(lo, hi, val, dec=2, step=None, suffix="") -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setObjectName("acctSpin")
            sb.setRange(lo, hi)
            sb.setDecimals(dec)
            sb.setValue(val)
            if step: sb.setSingleStep(step)
            if suffix: sb.setSuffix(suffix)
            sb.setFixedWidth(110)
            return sb

        # 날짜 / 시간봉 / 자본
        col1 = QFormLayout(); col1.setSpacing(6)
        self._bt_start = date_edit(90)
        self._bt_end   = date_edit(0)
        col1.addRow("시작일:", self._bt_start)
        col1.addRow("종료일:", self._bt_end)

        col2 = QFormLayout(); col2.setSpacing(6)
        self._bt_tf = QComboBox()
        self._bt_tf.setObjectName("modeCombo")
        for tf in ["5m", "15m", "30m", "1H", "6H", "1D"]:
            self._bt_tf.addItem(tf, tf)
        self._bt_tf.setCurrentText("1H")
        self._bt_tf.setFixedWidth(90)
        self._bt_capital = dspin(100, 10_000_000, 10_000, 0, 1000, " USDT")
        col2.addRow("시간봉:", self._bt_tf)
        col2.addRow("초기 자본:", self._bt_capital)

        col3 = QFormLayout(); col3.setSpacing(6)
        self._bt_fee      = dspin(0, 1, 0.05, 3, 0.01, " %")
        self._bt_slip     = dspin(0, 1, 0.02, 3, 0.01, " %")
        self._bt_size_pct = dspin(1, 100, 10, 0, 5, " %")
        col3.addRow("수수료:", self._bt_fee)
        col3.addRow("슬리피지:", self._bt_slip)
        col3.addRow("주문비율:", self._bt_size_pct)

        run_btn = QPushButton("▶  백테스트 실행")
        run_btn.setObjectName("longOrderBtn")
        run_btn.setFixedHeight(36)
        run_btn.clicked.connect(self._run_backtest)

        cfg_row.addLayout(col1)
        cfg_row.addLayout(col2)
        cfg_row.addLayout(col3)
        cfg_row.addWidget(run_btn, 0, Qt.AlignmentFlag.AlignBottom)
        cfg_row.addStretch()

        # 결과 표시
        self._bt_result = QTextEdit()
        self._bt_result.setObjectName("logView")
        self._bt_result.setReadOnly(True)
        self._bt_result.setFixedHeight(160)
        self._bt_result.setPlaceholderText("백테스트 실행 후 결과가 여기에 표시됩니다.")

        # 거래 로그 테이블
        bt_cols = ["진입시각", "청산시각", "방향", "진입가", "청산가", "결과", "수익률(%)"]
        self._bt_table = QTableWidget(0, len(bt_cols))
        self._bt_table.setObjectName("tradeTable")
        self._bt_table.setHorizontalHeaderLabels(bt_cols)
        self._bt_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bt_table.setAlternatingRowColors(True)
        self._bt_table.verticalHeader().setVisible(False)
        hdr = self._bt_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)

        root.addLayout(cfg_row)
        root.addWidget(self._bt_result)
        root.addWidget(self._bt_table, 1)
        return w

    def _run_backtest(self):
        """백테스트를 실행하고 결과를 탭에 표시합니다."""
        from datetime import datetime as dt_cls
        start_qd = self._bt_start.date()
        end_qd   = self._bt_end.date()
        start_ts = int(dt_cls(start_qd.year(), start_qd.month(), start_qd.day()).timestamp() * 1000)
        end_ts   = int(dt_cls(end_qd.year(),   end_qd.month(),   end_qd.day(), 23, 59, 59).timestamp() * 1000)

        cfg = BacktestConfig(
            start_ts        = start_ts,
            end_ts          = end_ts,
            timeframe       = self._bt_tf.currentData(),
            initial_capital = self._bt_capital.value(),
            fee_rate        = self._bt_fee.value() / 100,
            slippage        = self._bt_slip.value() / 100,
            order_size_pct  = self._bt_size_pct.value(),
        )

        self._bt_result.setPlainText("백테스트 실행 중...")
        QApplication.processEvents()

        try:
            result = Backtester().run(cfg)
        except Exception as exc:
            self._bt_result.setPlainText(f"오류: {exc}")
            return

        d = result.to_dict()
        lines = [
            f"기간: {self._bt_start.date().toString('yyyy-MM-dd')} ~ {self._bt_end.date().toString('yyyy-MM-dd')}",
            f"시간봉: {cfg.timeframe}    초기 자본: ${cfg.initial_capital:,.0f}",
            "",
            f"총 거래: {d['total_trades']}회   승: {d['win_trades']}   패: {d['loss_trades']}",
            f"승률:    {d['win_rate']:.1f}%",
            f"누적수익: {d['cumulative_return_pct']:+.2f}%",
            f"평균 수익: {d['avg_win_pct']:+.3f}%   평균 손실: {d['avg_loss_pct']:.3f}%",
            f"MDD:      {d['max_drawdown_pct']:.2f}%",
            f"손익비:   {d['profit_factor']:.2f}",
            f"익절: {d['tp_trades']}   손절: {d['sl_trades']}",
            f"최종 자본: ${d['final_capital']:,.2f}",
        ]
        self._bt_result.setPlainText("\n".join(lines))

        # 거래 로그 테이블 갱신
        RESULT_COLOR = {"TP1": GREEN, "TP2": GREEN, "SL": RED, "FORCED_CLOSE": YELLOW}

        def ts_str(ts_ms: int) -> str:
            try:
                from datetime import datetime as dtt
                return dtt.fromtimestamp(ts_ms / 1000).strftime("%y-%m-%d %H:%M")
            except Exception:
                return str(ts_ms)

        log = result.trade_log
        self._bt_table.setRowCount(len(log))
        for i, t in enumerate(log):
            res = t.get("result", "")
            rc  = RESULT_COLOR.get(res, TEXT2)
            pnl = t.get("pnl_pct", 0)
            pnl_c = GREEN if pnl >= 0 else RED

            def cell(txt, color=TEXT) -> QTableWidgetItem:
                item = QTableWidgetItem(str(txt))
                item.setForeground(QColor(color))
                return item

            self._bt_table.setItem(i, 0, cell(ts_str(t.get("entry_ts", 0)), TEXT2))
            self._bt_table.setItem(i, 1, cell(ts_str(t.get("exit_ts",  0)), TEXT2))
            self._bt_table.setItem(i, 2, cell(t.get("direction", ""), DIR_COLOR.get(t.get("direction",""), TEXT)))
            self._bt_table.setItem(i, 3, cell(f"${t.get('entry_px',0):,.2f}"))
            self._bt_table.setItem(i, 4, cell(f"${t.get('exit_px', 0):,.2f}"))
            self._bt_table.setItem(i, 5, cell(res, rc))
            self._bt_table.setItem(i, 6, cell(f"{pnl:+.3f}%", pnl_c))

    def _make_account_panel(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(16)

        # ── 잔고 ──
        bal_col = QVBoxLayout()
        bal_col.setSpacing(4)
        bal_hdr = QLabel("가용 잔고 (USDT)")
        bal_hdr.setObjectName("sectionHeader")
        self._bal_lbl   = QLabel("연동 안 됨")
        self._bal_lbl.setObjectName("acctValue")
        self._avail_lbl = QLabel("")
        self._avail_lbl.setObjectName("acctSub")
        bal_col.addWidget(bal_hdr)
        bal_col.addWidget(self._bal_lbl)
        bal_col.addWidget(self._avail_lbl)
        bal_col.addStretch()

        # ── 포지션 ──
        pos_col = QVBoxLayout()
        pos_col.setSpacing(4)
        pos_hdr = QLabel("현재 포지션")
        pos_hdr.setObjectName("sectionHeader")
        self._pos_lbl = QLabel("—")
        self._pos_lbl.setObjectName("acctValue")
        self._pos_sub = QLabel("")
        self._pos_sub.setObjectName("acctSub")
        pos_col.addWidget(pos_hdr)
        pos_col.addWidget(self._pos_lbl)
        pos_col.addWidget(self._pos_sub)
        pos_col.addStretch()

        # ── 수동 주문 ──
        order_col = QVBoxLayout()
        order_col.setSpacing(6)

        # 수량 행
        size_row = QHBoxLayout()
        size_row.setSpacing(6)
        size_lbl = QLabel("수량 (BTC)")
        size_lbl.setObjectName("acctSub")
        size_lbl.setFixedWidth(72)
        self._size_spin = QDoubleSpinBox()
        self._size_spin.setObjectName("acctSpin")
        self._size_spin.setRange(0.001, 100.0)
        self._size_spin.setSingleStep(0.001)
        self._size_spin.setDecimals(3)
        self._size_spin.setValue(self._risk_cfg.order_size_btc)
        self._size_spin.setFixedWidth(120)
        size_row.addWidget(size_lbl)
        size_row.addWidget(self._size_spin)
        size_row.addStretch()

        # 주문 버튼 행
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._long_btn  = QPushButton("▲  LONG")
        self._short_btn = QPushButton("▼  SHORT")
        self._close_btn = QPushButton("✕  청산")
        self._long_btn.setObjectName("longOrderBtn")
        self._short_btn.setObjectName("shortOrderBtn")
        self._close_btn.setObjectName("closeOrderBtn")
        for btn in (self._long_btn, self._short_btn, self._close_btn):
            btn.setFixedHeight(34)
        self._long_btn.clicked.connect(lambda: self._place_order("LONG"))
        self._short_btn.clicked.connect(lambda: self._place_order("SHORT"))
        self._close_btn.clicked.connect(self._close_position)
        btn_row.addWidget(self._long_btn)
        btn_row.addWidget(self._short_btn)
        btn_row.addWidget(self._close_btn)

        order_col.addLayout(size_row)
        order_col.addLayout(btn_row)
        order_col.addStretch()

        # ── 자동매매 ──
        auto_col = QVBoxLayout()
        auto_col.setSpacing(6)
        auto_hdr = QLabel("자동매매")
        auto_hdr.setObjectName("sectionHeader")

        self._auto_chk = QCheckBox("활성화")
        self._auto_chk.setObjectName("autoChk")
        self._auto_chk.setChecked(False)
        self._auto_chk.toggled.connect(self._on_auto_toggle)

        thresh_row = QHBoxLayout()
        thresh_row.setSpacing(6)
        thresh_lbl = QLabel("확정신호")
        thresh_lbl.setObjectName("acctSub")
        self._auto_spin = QDoubleSpinBox()
        self._auto_spin.setObjectName("acctSpin")
        self._auto_spin.setRange(0.0, 99.0)
        self._auto_spin.setSingleStep(5.0)
        self._auto_spin.setDecimals(0)
        self._auto_spin.setValue(self._risk_cfg.confidence_threshold)
        self._auto_spin.setSuffix(" %")
        self._auto_spin.setFixedWidth(80)
        self._auto_spin.valueChanged.connect(self._on_auto_threshold_changed)
        thresh_row.addWidget(thresh_lbl)
        thresh_row.addWidget(self._auto_spin)
        thresh_row.addStretch()

        auto_col.addWidget(auto_hdr)
        auto_col.addWidget(self._auto_chk)
        auto_col.addLayout(thresh_row)
        auto_col.addStretch()

        # API 미연동 시 실거래 수동 버튼만 비활성화합니다.
        # 모의매매 자동매매는 API 키 없이도 동작해야 합니다.
        self._set_order_buttons_enabled(self._private_client is not None)

        lay.addLayout(bal_col, 1)
        lay.addLayout(pos_col, 1)
        lay.addLayout(order_col, 2)
        lay.addLayout(auto_col, 1)
        return lay

    def _make_trade_table(self) -> QTableWidget:
        cols = [
            "구분", "진입시각", "방향", "진입가", "손절가",
            "익절1", "익절2", "청산가", "결과",
            "수익률(%)", "진입이유", "수익이유", "손실이유",
        ]
        tbl = QTableWidget(0, len(cols))
        tbl.setObjectName("tradeTable")
        tbl.setHorizontalHeaderLabels(cols)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)  # 진입이유
        hdr.setSectionResizeMode(11, QHeaderView.ResizeMode.Stretch)  # 수익이유
        hdr.setSectionResizeMode(12, QHeaderView.ResizeMode.Stretch)  # 손실이유
        return tbl

    def _make_tf_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, tf in enumerate(TIMEFRAMES):
            cell = TimeframeCell(tf)
            self._tf_cells[tf] = cell
            grid.addWidget(cell, i // 4, i % 4)
        return grid

    # ── Spinner ────────────────────────────────────────────────────────────────

    def _tick_spinner(self):
        self._spin_idx = (self._spin_idx + 1) % len(SPINNER)
        self._refresh_btn.setText(f"{SPINNER[self._spin_idx]}  Loading…")

    def _start_loading(self):
        self._refresh_btn.setEnabled(False)
        self._spin_timer.start(90)
        self._set_status("● SYNC", "statusLoading")

    def _stop_loading(self):
        self._spin_timer.stop()
        self._refresh_btn.setText("⟳  Refresh")
        self._refresh_btn.setEnabled(True)

    # ── Refresh logic ──────────────────────────────────────────────────────────

    def refresh(self):
        if self._future and not self._future.done():
            return
        self._start_loading()
        self._future = self._executor.submit(self._worker, not self._seeded)
        self._future.add_done_callback(self._emit_result)

    def _worker(self, needs_seed: bool):
        logs = []

        if needs_seed:
            self._signals.progress.emit("━━━ 초기 데이터 로딩 중… ━━━")
            logs.extend(self._seed(emit=True))
            self._signals.progress.emit("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 최신 캔들 소량 갱신 (병렬)
        errors = []
        limits = {tf: REFRESH_CANDLE_LIMIT for tf in TIMEFRAMES}
        for tf, candles, err in self._parallel_fetch(limits, emit_progress=False):
            if candles:
                insert_candles(SYMBOL, tf, candles)
            elif err:
                errors.append(f"{tf}: {err}")

        candles_by_tf = {
            tf: get_recent_candles(SYMBOL, tf, RECENT_CANDLE_LIMIT_BY_TIMEFRAME.get(tf, INITIAL_CANDLE_LIMIT))
            for tf in TIMEFRAMES
        }
        usable = {tf: c for tf, c in candles_by_tf.items() if c}
        if not usable:
            logs.append("[WARN] 캔들 데이터 없음. API/네트워크 확인 필요.")
            return None, errors, logs

        ath = get_all_time_high(SYMBOL, DEFAULT_TIMEFRAME)
        atl = get_all_time_low(SYMBOL, DEFAULT_TIMEFRAME)
        market = None
        try:
            market = self.clients["5m"].fetch_market_snapshot().to_dict()
        except Exception as exc:
            errors.append(f"market: {exc}")
        equity = None
        if self._cached_account:
            try:
                equity = float(self._cached_account.get("accountEquity") or self._cached_account.get("equity") or 0) or None
            except (TypeError, ValueError):
                equity = None
        result = self.engine.analyze_multi_timeframe(
            usable,
            all_time_high=ath,
            all_time_low=atl,
            market=market,
            account_equity=equity,
        ).to_dict()
        insert_signal(SYMBOL, DEFAULT_TIMEFRAME, result)
        return result, errors, logs

    def _seed(self, emit: bool = False) -> list[str]:
        logs = []
        if not USE_DEMO_DATA:
            for tf in TIMEFRAMES:
                n = purge_unaligned_candles(SYMBOL, tf)
                if n:
                    logs.append(f"{tf}: 비정렬 캔들 {n}개 제거")

        fetch_limits = {}
        for tf in TIMEFRAMES:
            required = RECENT_CANDLE_LIMIT_BY_TIMEFRAME.get(tf, INITIAL_CANDLE_LIMIT)
            if len(get_recent_candles(SYMBOL, tf, required)) >= required:
                if emit:
                    self._signals.progress.emit(f"  ✓ {tf:<4}  캐시 데이터 사용")
                continue
            fetch_limits[tf] = required

        if not fetch_limits:
            return logs

        with ThreadPoolExecutor(max_workers=min(8, len(fetch_limits))) as ex:
            fmap = {
                ex.submit(self.clients[tf].fetch_recent_or_demo, lim): tf
                for tf, lim in fetch_limits.items()
            }
            for future in as_completed(fmap):
                tf = fmap[future]
                try:
                    candles, err = future.result()
                except Exception as exc:
                    candles, err = [], str(exc)
                if candles:
                    insert_candles(SYMBOL, tf, candles)
                    if emit:
                        self._signals.progress.emit(f"  ✓ {tf:<4}  {len(candles)}개 저장")
                    logs.append(f"{tf}: {len(candles)}개 초기 저장")
                else:
                    if emit:
                        self._signals.progress.emit(f"  ✗ {tf:<4}  API 오류")
                    logs.append(f"{tf}: 로드 실패 — {err}")
        return logs

    def _parallel_fetch(
        self, limits: dict[str, int], emit_progress: bool = False
    ) -> list[tuple[str, list[dict], str | None]]:
        if not limits:
            return []
        results = []
        with ThreadPoolExecutor(max_workers=min(8, len(limits))) as ex:
            fmap = {
                ex.submit(self.clients[tf].fetch_recent_or_demo, lim): tf
                for tf, lim in limits.items()
            }
            for future in as_completed(fmap):
                tf = fmap[future]
                try:
                    candles, err = future.result()
                except Exception as exc:
                    candles, err = [], str(exc)
                results.append((tf, candles, err))
        return sorted(results, key=lambda x: TIMEFRAMES.index(x[0]))

    def _emit_result(self, future):
        try:
            out = future.result()
        except Exception as exc:
            self._signals.failed.emit(str(exc))
            return
        self._signals.completed.emit(*out)

    # ── UI updates (main thread) ───────────────────────────────────────────────

    def _on_done(self, result, errors, logs):
        self._seeded = True
        self._stop_loading()
        for line in logs:
            self._log(line)
        if result is None:
            self._set_status("● ERROR", "statusError")
            return
        self._render(result, errors)

    def _on_failed(self, msg: str):
        self._stop_loading()
        self._set_status("● ERROR", "statusError")
        self._log(f"[FAIL] {msg}")

    def _render(self, r: dict, errors: list[str]):
        # 자동매매/모의매매는 명시적으로 활성화된 경우에만 진입합니다.
        self._check_auto_trade(r)

        direction = r.get("direction", "HOLD")
        summary = (r.get("timeframe_summary") or {}).get("1m") or (r.get("timeframe_summary") or {}).get("5m") or {}
        planned_direction = r.get("planned_direction") or summary.get("plan_direction") or direction
        display_direction = f"WAIT {planned_direction}" if direction == "HOLD" and planned_direction in ("LONG", "SHORT") else direction
        display_key = planned_direction if direction == "HOLD" and planned_direction in ("LONG", "SHORT") else direction
        d_color = DIR_COLOR.get(display_key, TEXT2)
        d_bg    = DIR_BG.get(display_key, CARD)
        d_arrow = DIR_ARROW.get(display_key, "—")

        # Price
        price = r.get("last_price") or r.get("analysis_price") or r.get("entry_price", 0)
        self._price_lbl.setText(f"${price:,.2f}")

        # Direction badge
        self._dir_badge.setText(f"{d_arrow}  {display_direction}")
        self._dir_badge.setStyleSheet(
            f"color: {d_color}; background: {d_bg}; "
            f"border: 1px solid {d_color}; border-radius: 8px; "
            f"font-size: 18px; font-weight: 800;"
        )

        # Strategy / wait state
        strategy_signal = r.get("strategy_signal", "HOLD")
        strategy_color = YELLOW if strategy_signal.startswith("WAIT") else d_color if direction in ("LONG", "SHORT") else TEXT2
        self._conf_lbl.setText(strategy_signal)
        self._conf_lbl.setStyleSheet(f"color: {strategy_color};")

        strategy_state = r.get("market_mode", "HOLD")
        self._ath_lbl.setText(f"State: {strategy_state}")
        self._ath_lbl.setStyleSheet(f"color: {YELLOW if str(strategy_state).startswith('WAIT') else TEXT2};")
        support = summary.get("support_level")
        breakout = summary.get("breakout_level")
        level_text = f"${support:,.2f}" if support is not None else f"${breakout:,.2f}" if breakout is not None else "—"
        self._atl_lbl.setText(f"Plan: {planned_direction} @ {level_text}")
        self._atl_lbl.setStyleSheet(f"color: {TEXT2};")

        # Strategy context bars
        rsi = summary.get("rsi14")
        volume_ratio = summary.get("volume_ratio")
        rsi_val = float(rsi) if rsi is not None else 0.0
        vol_val = float(volume_ratio) if volume_ratio is not None else 0.0
        self._long_bar.update(f"RSI14    {rsi_val:5.1f}", int(max(0, min(100, rsi_val))))
        self._short_bar.update(f"VOLUME   {vol_val:5.2f}x", int(max(0, min(100, vol_val * 50))))

        # Risk cards
        # 포지션이 열려있으면 진입 시점의 값을 고정 표시, 아니면 최신 분석값 표시
        def fmt(v):
            return f"${v:,.2f}" if v is not None else "—"

        if self._open_trade_data:
            t = self._open_trade_data
            self._risk_cards["entry"].update(fmt(t.get("entry")), TEXT)
            self._risk_cards["stop"].update(fmt(t.get("sl")), RED)
            self._risk_cards["tp1"].update(fmt(t.get("tp1")), GREEN)
            self._risk_cards["tp2"].update(fmt(t.get("tp2")), GREEN)
            rr = r.get("risk_reward_ratio")
            self._risk_cards["rr"].update(f"1 : {rr}" if rr else "—", YELLOW)
        else:
            self._risk_cards["entry"].update(fmt(r.get("entry_price")), TEXT)
            self._risk_cards["stop"].update(fmt(r.get("stop_loss")), RED)
            self._risk_cards["tp1"].update(fmt(r.get("take_profit_1")), GREEN)
            self._risk_cards["tp2"].update(fmt(r.get("take_profit_2")), GREEN)
            rr = r.get("risk_reward_ratio")
            self._risk_cards["rr"].update(f"1 : {rr}" if rr else "—", YELLOW)

        # Timeframe cells
        directions = r.get("timeframe_directions", {})
        for tf, cell in self._tf_cells.items():
            cell.set_direction(directions.get(tf, "HOLD"))

        # Timestamp
        now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        self._updated_lbl.setText(f"Updated: {now}")

        # Status
        if errors:
            self._set_status("● STALE", "statusError")
            self._log("[WARN] API 오류:\n  " + "\n  ".join(errors))
        else:
            label = "● LIVE" if not USE_DEMO_DATA else "● DEMO"
            obj   = "statusLive" if not USE_DEMO_DATA else "statusDemo"
            self._set_status(label, obj)

        # Reasons
        reasons = r.get("reasons", [])
        if reasons:
            self._log("\n".join(f"  • {ln}" for ln in reasons))
            self._log("─" * 64)

    def _log(self, text: str):
        self._log_view.append(text)

    def _set_status(self, text: str, obj_name: str):
        self._status_lbl.setText(text)
        self._status_lbl.setObjectName(obj_name)
        self._status_lbl.style().unpolish(self._status_lbl)
        self._status_lbl.style().polish(self._status_lbl)

    # ── Real-time price ────────────────────────────────────────────────────────

    def _fetch_price(self):
        """백그라운드에서 현재가를 조회하고 price_updated 신호로 전달합니다."""
        if self._price_future and not self._price_future.done():
            return  # 이전 요청이 아직 진행 중이면 건너뜀
        self._price_future = self._price_executor.submit(self._worker_price)
        self._price_future.add_done_callback(self._emit_price)

    def _worker_price(self) -> float | None:
        try:
            # 5m 클라이언트(ticker 조회는 timeframe 무관)를 재사용
            snap = self.clients.get("5m") and self.clients["5m"].fetch_market_snapshot()
            return snap and (snap.last_price or snap.mark_price)
        except Exception:
            return None

    def _emit_price(self, future: Future):
        try:
            price = future.result()
        except Exception:
            price = None
        if price:
            self._signals.price_updated.emit(price)

    def _on_price_update(self, price: float):
        self._last_price = price
        self._price_lbl.setText(f"${price:,.2f}")
        self._updated_lbl.setText(f"Updated: {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
        if self._open_trade_id and self._open_trade_data:
            self._check_tp_sl(price)
        # 모의매매 TP/SL 감시
        if self._paper_trader.is_open:
            self._check_paper_tp_sl(price)

    def _check_paper_tp_sl(self, price: float):
        result_code = self._paper_trader.check_tp_sl(price)
        if not result_code:
            return
        t     = self._paper_trader.open_data
        entry = t["entry"]
        direction = t["direction"]
        pnl_pct = (
            (price - entry) / entry * 100 if direction == "LONG"
            else (entry - price) / entry * 100
        )
        sign = "+" if pnl_pct >= 0 else ""
        if result_code.startswith("TP"):
            profit_reason = (
                f"[모의] {result_code} 적중: ${entry:,.2f} → ${price:,.2f}  ({sign}{pnl_pct:.2f}%)"
            )
            loss_reason = ""
        else:
            profit_reason = ""
            loss_reason = (
                f"[모의] 손절: ${entry:,.2f} → ${price:,.2f}  ({sign}{pnl_pct:.2f}%)"
            )
        tid, pnl = self._paper_trader.close_trade(
            exit_price=price, result=result_code,
            profit_reason=profit_reason, loss_reason=loss_reason,
        )
        self._risk_mgr.record_trade_result(pnl)
        emoji = "익절" if result_code.startswith("TP") else "손절"
        self._log(f"[모의매매 {emoji}] #{tid}  {result_code}  {sign}{pnl:.2f}%")
        self._refresh_trade_table()
        self._tabs.setCurrentIndex(1)

    # ── Trade tracking ─────────────────────────────────────────────────────────

    def _handle_trade_signal(self, r: dict):
        """
        포지션 관리 규칙:
          - 포지션 없음 + LONG/SHORT → 신규 진입
          - 포지션 있음 + 같은 방향  → 유지 (아무것도 안 함)
          - 포지션 있음 + HOLD       → 유지 (TP/SL에 맡김)
          - 포지션 있음 + 반대 방향  → 무시 (TP/SL에 맡김)
        """
        new_dir = r.get("direction", "HOLD")

        if self._open_trade_data:
            return
        else:
            # 포지션 없음 → LONG/SHORT이면 새 진입
            if new_dir in ("LONG", "SHORT"):
                self._do_open_trade(new_dir, r)

    def _do_open_trade(self, direction: str, r: dict):
        """신규 포지션을 DB에 기록하고 추적 상태를 설정합니다."""
        entry   = r.get("entry_price") or 0.0
        reasons = "\n".join(r.get("reasons", []))
        trade_id = open_trade(
            symbol        = SYMBOL,
            direction     = direction,
            entry_price   = entry,
            stop_loss     = r.get("stop_loss"),
            take_profit_1 = r.get("take_profit_1"),
            take_profit_2 = r.get("take_profit_2"),
            risk_reward   = r.get("risk_reward_ratio"),
            confidence    = r.get("confidence", 0),
            long_prob     = r.get("long_probability", 50),
            short_prob    = r.get("short_probability", 50),
            tf_directions = r.get("timeframe_directions", {}),
            entry_reason  = reasons,
        )
        self._open_trade_id   = trade_id
        self._open_trade_data = {
            "direction": direction,
            "entry":     entry,
            "sl":        r.get("stop_loss"),
            "tp1":       r.get("take_profit_1"),
            "tp2":       r.get("take_profit_2"),
        }
        self._log(f"[TRADE #{trade_id}] {direction} 진입  ${entry:,.2f}  SL=${r.get('stop_loss') or 0:,.2f}")
        self._refresh_trade_table()

    def _check_tp_sl(self, price: float):
        """현재가가 TP/SL에 도달했는지 확인하고 자동 청산합니다."""
        t = self._open_trade_data
        direction = t["direction"]
        sl  = t.get("sl")
        tp1 = t.get("tp1")
        tp2 = t.get("tp2")
        entry = t["entry"]

        result_code: str | None = None
        if direction == "LONG":
            if tp2 and price >= tp2:
                result_code = "TP2"
            elif tp1 and price >= tp1:
                result_code = "TP1"
            elif sl and price <= sl:
                result_code = "SL"
        elif direction == "SHORT":
            if tp2 and price <= tp2:
                result_code = "TP2"
            elif tp1 and price <= tp1:
                result_code = "TP1"
            elif sl and price >= sl:
                result_code = "SL"

        if not result_code:
            return

        pnl_pct = (
            (price - entry) / entry * 100 if direction == "LONG"
            else (entry - price) / entry * 100
        )
        sign = "+" if pnl_pct >= 0 else ""
        profit_reason = ""
        loss_reason   = ""
        if result_code.startswith("TP"):
            profit_reason = (
                f"{result_code} 적중: 진입 ${entry:,.2f} → 청산 ${price:,.2f}  "
                f"({sign}{pnl_pct:.2f}%)\n"
                f"방향({direction}) 예측이 맞았고 목표가에 도달했습니다."
            )
        else:
            loss_reason = (
                f"손절 발동: 진입 ${entry:,.2f} → 청산 ${price:,.2f}  "
                f"({sign}{pnl_pct:.2f}%)\n"
                f"가격이 ATR 기준 손절가를 돌파했습니다."
            )

        trade_id_closed = self._open_trade_id
        close_trade(
            trade_id      = trade_id_closed,
            exit_price    = price,
            result        = result_code,
            pnl_pct       = pnl_pct,
            profit_reason = profit_reason,
            loss_reason   = loss_reason,
        )

        sign = "+" if pnl_pct >= 0 else ""
        emoji = "익절" if result_code.startswith("TP") else "손절"
        self._log("━" * 60)
        self._log(
            f"[{emoji}] TRADE #{trade_id_closed}  {result_code}\n"
            f"  방향: {t['direction']}  진입 ${entry:,.2f} → 청산 ${price:,.2f}\n"
            f"  수익률: {sign}{pnl_pct:.2f}%"
        )
        self._log("━" * 60)

        self._open_trade_id   = None
        self._open_trade_data = None
        self._refresh_trade_table()
        # 복기 탭으로 자동 전환
        self._tabs.setCurrentIndex(1)

    def _force_close_trade(self, price: float, result_code: str):
        """시그널 변경 등으로 강제 청산합니다."""
        if not self._open_trade_id or not self._open_trade_data:
            return
        t = self._open_trade_data
        entry = t["entry"]
        pnl_pct = (
            (price - entry) / entry * 100 if t["direction"] == "LONG"
            else (entry - price) / entry * 100
        )
        profit_reason = ""
        loss_reason   = ""
        msg = f"시그널 변경으로 강제 청산: ${entry:,.2f} → ${price:,.2f}  ({'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%)"
        if pnl_pct >= 0:
            profit_reason = msg
        else:
            loss_reason = msg

        trade_id_closed = self._open_trade_id
        close_trade(
            trade_id      = trade_id_closed,
            exit_price    = price,
            result        = result_code,
            pnl_pct       = pnl_pct,
            profit_reason = profit_reason,
            loss_reason   = loss_reason,
        )
        sign = "+" if pnl_pct >= 0 else ""
        self._log(
            f"[시그널변경 청산] TRADE #{trade_id_closed}  ${entry:,.2f} → ${price:,.2f}  ({sign}{pnl_pct:.2f}%)"
        )
        self._open_trade_id   = None
        self._open_trade_data = None

    def _refresh_trade_table(self):
        """DB에서 최근 거래를 읽어 테이블을 갱신합니다."""
        try:
            self._render_trade_table()
        except Exception as exc:
            self._log(f"[ERR] 복기 테이블 갱신 실패: {exc}")

    def _render_trade_table(self):
        trades = get_recent_trades(SYMBOL, 50)
        tbl = self._trade_table
        tbl.setRowCount(0)          # 기존 행 완전 제거 후 재추가
        tbl.setRowCount(len(trades))

        RESULT_COLOR = {
            "TP1": GREEN, "TP2": GREEN,
            "SL":  RED,
            "SIGNAL_CHANGE": YELLOW,
            "OPEN": BLUE,
        }

        def make_cell(text, color: str = TEXT) -> QTableWidgetItem:
            val = str(text) if text is not None else "—"
            item = QTableWidgetItem(val)
            item.setForeground(QColor(color))
            item.setToolTip(val)
            return item

        for row, t in enumerate(trades):
            result  = t.get("result") or "OPEN"
            r_color = RESULT_COLOR.get(result, TEXT2)
            pnl     = t.get("pnl_pct")

            if pnl is not None:
                sign    = "+" if pnl >= 0 else ""
                pnl_str = f"{sign}{pnl:.2f}%"
                pnl_c   = GREEN if pnl >= 0 else RED
            else:
                pnl_str = "진행중"
                pnl_c   = BLUE

            def fmt_price(v):
                return f"${v:,.2f}" if v else "—"

            entry_time  = (t.get("entry_time") or "")[:16]
            direction   = t.get("direction", "")
            trade_type  = t.get("trade_type", "LIVE")
            type_color  = PURPLE if trade_type == "PAPER" else BLUE

            tbl.setItem(row, 0,  make_cell(trade_type,                                  type_color))
            tbl.setItem(row, 1,  make_cell(entry_time,                                  TEXT2))
            tbl.setItem(row, 2,  make_cell(direction,   DIR_COLOR.get(direction, TEXT)))
            tbl.setItem(row, 3,  make_cell(fmt_price(t.get("entry_price"))))
            tbl.setItem(row, 4,  make_cell(fmt_price(t.get("stop_loss")),                RED))
            tbl.setItem(row, 5,  make_cell(fmt_price(t.get("take_profit_1")),            GREEN))
            tbl.setItem(row, 6,  make_cell(fmt_price(t.get("take_profit_2")),            GREEN))
            tbl.setItem(row, 7,  make_cell(fmt_price(t.get("exit_price"))))
            tbl.setItem(row, 8,  make_cell(result,                                       r_color))
            tbl.setItem(row, 9,  make_cell(pnl_str,                                      pnl_c))
            tbl.setItem(row, 10, make_cell(t.get("entry_reason")  or "—",                TEXT2))
            tbl.setItem(row, 11, make_cell(t.get("profit_reason") or "—",                GREEN))
            tbl.setItem(row, 12, make_cell(t.get("loss_reason")   or "—",                RED))

    # ── Auto-trade ─────────────────────────────────────────────────────────────

    def _on_auto_toggle(self, checked: bool):
        if checked and self._trading_mode == TradingMode.LIVE_TRADING:
            ans = QMessageBox.question(
                self, "실거래 자동매매 확인",
                "⚠ 실거래(LIVE_TRADING) 모드에서 자동매매를 활성화합니다.\n"
                "실제 Bitget 주문이 자동으로 발생합니다.\n\n"
                "계속하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                self._auto_chk.setChecked(False)
                return
        self._auto_trade_enabled = checked
        state = "ON" if checked else "OFF"
        self._log(f"[자동매매] {state}  모드={self._trading_mode.value}  확정신호 기준={self._auto_threshold:.0f}%")
        ok, power_msg = keep_awake.enable() if checked else keep_awake.disable()
        self._log(f"[전원관리] {power_msg}" if ok else f"[전원관리 경고] {power_msg}")

    def _on_auto_threshold_changed(self, value: float):
        self._auto_threshold = value
        self._risk_cfg.confidence_threshold = value
        self._risk_mgr.settings.confidence_threshold = value

    def _on_mode_changed(self, index: int):
        data = self._mode_combo.currentData()
        # QComboBox가 enum을 문자열로 반환할 수 있으므로 변환
        new_mode = TradingMode(data) if isinstance(data, str) else data
        if new_mode == TradingMode.LIVE_TRADING:
            ans = QMessageBox.question(
                self, "실거래 모드 전환 확인",
                "⚠ LIVE_TRADING 모드로 전환합니다.\n"
                "리스크 설정에서 '실거래 허용' 체크 및 API 키 확인 후 사용하세요.\n\n"
                "계속하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                self._mode_combo.blockSignals(True)
                modes = list(TradingMode)
                self._mode_combo.setCurrentIndex(modes.index(self._trading_mode))
                self._mode_combo.blockSignals(False)
                return
        self._trading_mode = new_mode
        self._log(f"[모드변경] {new_mode.value} ({new_mode.label()})")

    def _emergency_stop(self):
        """긴급정지: 자동매매 즉시 OFF + 추가 주문 차단."""
        self._risk_mgr.activate_emergency_stop()
        self._auto_trade_enabled = False
        self._auto_chk.setChecked(False)
        keep_awake.disable()
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log(f"[긴급정지] {now_str} — 자동매매 차단됨")
        self._emergency_btn.setStyleSheet(
            f"background: {RED}; color: white; border-color: {RED}; font-weight: 900;"
        )

        # 포지션 있으면 청산 여부 확인
        if self._open_trade_data or (self._private_client and self._cached_positions):
            ans = QMessageBox.question(
                self, "긴급정지 — 포지션 청산",
                "현재 포지션이 감지됐습니다.\n\n"
                "지금 시장가로 청산하시겠습니까?\n"
                "(아니오 선택 시 포지션은 그대로 유지됩니다)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Yes:
                if self._private_client:
                    try:
                        for p in self._cached_positions:
                            if p.get("symbol") == SYMBOL:
                                self._private_client.close_position(
                                    p.get("holdSide", "long")
                                )
                        self._log("[긴급정지] 거래소 포지션 청산 완료")
                        QTimer.singleShot(2000, self._fetch_account)
                    except Exception as exc:
                        self._log(f"[긴급정지] 청산 실패: {exc}")
                if self._open_trade_data and self._last_price:
                    self._force_close_trade(self._last_price, "SIGNAL_CHANGE")

    def _check_auto_trade(self, r: dict):
        """
        자동매매 진입 검사 (RiskManager 통해 안전조건 확인).
        모드에 따라 실거래 또는 모의매매로 분기합니다.
        """
        if not self._auto_trade_enabled:
            return
        if self._trading_mode == TradingMode.SIGNAL_ONLY:
            return

        direction  = r.get("direction", "HOLD")
        confidence = r.get("confidence", 0.0)

        # RiskManager 안전조건 검사
        allowed, reason = self._risk_mgr.check_entry(
            direction        = direction,
            confidence       = confidence,
            mode             = self._trading_mode,
            cached_positions = self._cached_positions,
            private_client   = self._private_client,
            entry_price      = r.get("entry_price"),
            stop_loss        = r.get("stop_loss"),
            entry_grade      = r.get("entry_grade"),
            risk_warnings    = r.get("risk_warnings", []),
        )
        if not allowed:
            # 이유가 있으면 로그에 남기되, 같은 이유 반복 시 스팸 방지
            if reason and "이미" not in reason:
                self._log(f"[자동매매 차단] {reason}")
            return

        # 모의매매 분기
        if self._trading_mode == TradingMode.PAPER_TRADING:
            self._auto_paper_trade(direction, r, reason)
        elif self._trading_mode == TradingMode.LIVE_TRADING:
            self._auto_live_trade(direction, r, reason)

    def _auto_paper_trade(self, direction: str, r: dict, entry_reason: str):
        """모의매매 자동 진입."""
        if self._paper_trader.is_open:
            return

        trade_id = self._paper_trader.open_trade(direction, r)
        self._log(
            f"[모의매매] {direction} 진입  #{trade_id}  "
            f"전략신호={r.get('strategy_signal', direction)}"
        )
        self._risk_mgr.record_order_placed()
        self._refresh_trade_table()

    def _auto_live_trade(self, direction: str, r: dict, entry_reason: str):
        """실거래 자동 진입 (RiskManager 통과 후 실행)."""
        btc_positions = [p for p in self._cached_positions if p.get("symbol") == SYMBOL]
        if btc_positions or getattr(self, "_pending_live_order_id", None):
            return

        size = f"{self._risk_cfg.order_size_btc:.3f}"
        side = "buy" if direction == "LONG" else "sell"
        try:
            limit_price = float(r.get("entry_price") or 0)
            result = self._private_client.place_limit_order(side, size, f"{limit_price:.1f}", "open")
            order_id = result.get("orderId", "?")
            self._pending_live_order_id = str(order_id)
            self._log(
                f"[자동매매 LIVE 지정가] {direction} {size} BTC @ ${limit_price:,.1f}  "
                f"전략신호={r.get('strategy_signal', direction)}  orderId={order_id}"
            )
            self._risk_mgr.record_order_placed()
            QTimer.singleShot(2000, self._fetch_account)
        except Exception as exc:
            self._log(f"[자동매매] 주문 실패 (ORDER_FAILED): {exc}")

    # ── Account ────────────────────────────────────────────────────────────────

    def _make_private_client(self) -> "BitgetPrivateClient | None":
        c = creds_store.load()
        if c.is_set():
            return BitgetPrivateClient(c.api_key, c.secret_key, c.passphrase)
        return None

    def _open_settings(self):
        dlg = CredentialsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._creds         = creds_store.load()
            self._private_client = self._make_private_client()
            self._set_order_buttons_enabled(self._private_client is not None)
            if self._private_client:
                self._account_timer.start(10000)
                self._fetch_account()
                self._log("[API] 자격증명 저장 완료. 계정 조회 중...")
            else:
                self._account_timer.stop()
                self._log("[API] 자격증명이 비어 있습니다.")

    def _set_order_buttons_enabled(self, enabled: bool):
        for btn in (self._long_btn, self._short_btn, self._close_btn):
            btn.setEnabled(enabled)
        self._auto_chk.setEnabled(True)
        self._auto_spin.setEnabled(True)

    def _fetch_account(self):
        if not self._private_client:
            return
        if self._account_future and not self._account_future.done():
            return
        self._account_future = self._account_executor.submit(self._worker_account)
        self._account_future.add_done_callback(self._emit_account)

    def _worker_account(self):
        try:
            acct = self._private_client.get_account()
            pos  = self._private_client.get_positions()
            return acct, pos
        except Exception as exc:
            return None, str(exc)

    def _emit_account(self, future: Future):
        try:
            result = future.result()
        except Exception:
            result = (None, "조회 실패")
        self._signals.account_updated.emit(*result)

    def _on_account_update(self, acct, positions):
        if acct is None:
            self._bal_lbl.setText("조회 실패")
            self._bal_lbl.setStyleSheet(f"color: {RED};")
            if isinstance(positions, str):
                self._log(f"[계정] {positions}")
            return
        self._cached_account = acct
        self._cached_positions = positions if isinstance(positions, list) else []

        equity    = float(acct.get("accountEquity") or acct.get("equity") or 0)
        available = float(acct.get("available") or acct.get("crossMaxAvailable") or 0)
        upl       = float(acct.get("unrealizedPL") or 0)

        self._bal_lbl.setText(f"${equity:,.2f} USDT")
        self._bal_lbl.setStyleSheet(f"color: {TEXT};")
        upl_color = GREEN if upl >= 0 else RED
        self._avail_lbl.setText(
            f"가용: ${available:,.2f}   미실현손익: "
            f"<span style='color:{upl_color}'>{'+' if upl >= 0 else ''}{upl:,.2f}</span>"
        )
        self._avail_lbl.setTextFormat(Qt.TextFormat.RichText)

        btc_pos = [p for p in (positions or []) if p.get("symbol") == SYMBOL]
        if btc_pos:
            self._pending_live_order_id = None
        if btc_pos:
            p       = btc_pos[0]
            side    = p.get("holdSide", "").upper()
            total   = float(p.get("total") or 0)
            avg_px  = float(p.get("openPriceAvg") or 0)
            pnl_p   = float(p.get("unrealizedPL") or 0)
            s_color = GREEN if side == "LONG" else RED
            pnl_c   = GREEN if pnl_p >= 0 else RED
            self._pos_lbl.setText(f"{side}  {total} BTC")
            self._pos_lbl.setStyleSheet(f"color: {s_color}; font-weight: 800;")
            self._pos_sub.setText(
                f"평균단가: ${avg_px:,.2f}   "
                f"<span style='color:{pnl_c}'>{'+' if pnl_p >= 0 else ''}{pnl_p:,.2f} USDT</span>"
            )
            self._pos_sub.setTextFormat(Qt.TextFormat.RichText)
        else:
            self._pos_lbl.setText("포지션 없음")
            self._pos_lbl.setStyleSheet(f"color: {TEXT2};")
            self._pos_sub.setText("")

    def _place_order(self, direction: str):
        if not self._private_client:
            return
        size = f"{self._size_spin.value():.3f}"
        side = "buy" if direction == "LONG" else "sell"
        if not self._last_price:
            QMessageBox.warning(self, "주문 불가", "현재가를 확인할 수 없어 지정가를 계산하지 못했습니다.")
            return
        limit_price = self._last_price - 150.0 if direction == "LONG" else self._last_price + 150.0

        ans = QMessageBox.question(
            self, "주문 확인",
            f"⚠ 실제 주문이 발생합니다.\n\n"
            f"방향: {direction}\n수량: {size} BTC\n지정가: ${limit_price:,.1f}\n\n진행하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._private_client.place_limit_order(side, size, f"{limit_price:.1f}", "open")
            self._log(
                f"[지정가 주문 완료] {direction} {size} BTC @ ${limit_price:,.1f}  "
                f"orderId={result.get('orderId', '?')}"
            )
            QTimer.singleShot(2000, self._fetch_account)
        except Exception as exc:
            self._log(f"[주문 실패] {exc}")
            QMessageBox.critical(self, "주문 실패", str(exc))

    def _close_position(self):
        if not self._private_client:
            return
        # 현재 포지션 방향 파악
        try:
            positions = self._private_client.get_positions()
        except Exception as exc:
            self._log(f"[포지션 조회 실패] {exc}")
            return

        btc_pos = [p for p in positions if p.get("symbol") == SYMBOL]
        if not btc_pos:
            QMessageBox.information(self, "알림", "청산할 포지션이 없습니다.")
            return

        hold_side = btc_pos[0].get("holdSide", "long")
        size      = float(btc_pos[0].get("total") or 0)

        ans = QMessageBox.question(
            self, "청산 확인",
            f"⚠ 실제 청산 주문이 발생합니다.\n\n"
            f"포지션: {hold_side.upper()}  {size} BTC\n\n전량 시장가 청산하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return

        try:
            self._private_client.close_position(hold_side)
            self._log(f"[청산 완료] {hold_side.upper()}  {size} BTC")
            QTimer.singleShot(2000, self._fetch_account)
        except Exception as exc:
            self._log(f"[청산 실패] {exc}")
            QMessageBox.critical(self, "청산 실패", str(exc))

    def closeEvent(self, event):
        keep_awake.disable()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._price_executor.shutdown(wait=False, cancel_futures=True)
        self._account_executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

    # ── Stylesheet ─────────────────────────────────────────────────────────────

    @staticmethod
    def _css() -> str:
        return f"""
        /* ── Root ── */
        QWidget#root {{
            background: {BG};
            color: {TEXT};
            font-family: "Segoe UI", "Malgun Gothic", Arial, sans-serif;
            font-size: 13px;
        }}
        QWidget#tabPage {{
            background: {PANEL};
            color: {TEXT};
        }}
        QWidget#tabPage QLabel {{
            color: {TEXT};
            background: transparent;
            font-size: 12px;
            font-weight: 700;
        }}
        QWidget#tabPage QFormLayout {{
            background: {PANEL};
        }}
        QLabel {{
            color: {TEXT};
            background: transparent;
        }}

        /* ── Header ── */
        QLabel#symbol {{
            color: {TEXT};
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        QLabel#symSub {{
            color: {TEXT2};
            font-size: 11px;
        }}
        QLabel#updated {{
            color: {TEXT2};
            font-size: 12px;
            padding-right: 4px;
        }}

        /* ── Section headers ── */
        QLabel#sectionHeader {{
            color: {TEXT2};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 2px;
            padding-bottom: 3px;
        }}

        /* ── Status badges ── */
        QLabel#statusLive, QLabel#statusDemo,
        QLabel#statusError, QLabel#statusLoading {{
            border-radius: 5px;
            font-size: 11px;
            font-weight: 800;
            padding: 5px 10px;
            letter-spacing: 0.3px;
        }}
        QLabel#statusLive    {{ background:{GREEN_DIM}; color:{GREEN};  border:1px solid {GREEN};  }}
        QLabel#statusDemo    {{ background:{YELLOW_DIM};color:{YELLOW}; border:1px solid {YELLOW}; }}
        QLabel#statusError   {{ background:{RED_DIM};   color:{RED};    border:1px solid {RED};    }}
        QLabel#statusLoading {{ background:{BLUE_DIM};  color:{BLUE};   border:1px solid {BLUE};   }}

        /* ── Refresh button ── */
        QPushButton#refreshBtn {{
            background: {PANEL};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 6px;
            font-size: 13px;
            font-weight: 700;
            padding: 7px 14px;
        }}
        QPushButton#refreshBtn:hover {{
            border-color: {BLUE};
            color: {BLUE};
        }}
        QPushButton#refreshBtn:disabled {{
            color: {TEXT2};
        }}

        /* ── Hero ── */
        QLabel#priceHero {{
            color: {TEXT};
            font-size: 40px;
            font-weight: 800;
            letter-spacing: -1px;
            font-family: "Consolas", "Courier New", monospace;
        }}
        QLabel#dirBadge {{
            border-radius: 8px;
        }}
        QLabel#confLbl {{
            font-size: 22px;
            font-weight: 800;
            font-family: "Consolas", "Courier New", monospace;
        }}
        QLabel#modeLbl {{
            font-size: 12px;
            font-weight: 700;
            color: {TEXT2};
        }}

        /* ── Score bars ── */
        QLabel#barLabel {{
            color: {TEXT};
            font-size: 12px;
            font-weight: 700;
            font-family: "Consolas", "Courier New", monospace;
        }}
        QProgressBar#longBar {{
            background: {PANEL};
            border: none;
            border-radius: 7px;
        }}
        QProgressBar#longBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {GREEN_DIM}, stop:1 {GREEN});
            border-radius: 7px;
        }}
        QProgressBar#shortBar {{
            background: {PANEL};
            border: none;
            border-radius: 7px;
        }}
        QProgressBar#shortBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {RED_DIM}, stop:1 {RED});
            border-radius: 7px;
        }}

        /* ── Risk cards ── */
        QFrame#riskCard {{
            background: {CARD};
            border: 1px solid {BORDER};
            border-radius: 8px;
        }}
        QLabel#riskTitle {{
            color: {TEXT2};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QLabel#riskValue {{
            color: {TEXT};
            font-size: 15px;
            font-weight: 700;
            font-family: "Consolas", "Courier New", monospace;
        }}

        /* ── Timeframe cells ── */
        QFrame#tfCell {{
            background: {CARD};
            border: 1px solid {BORDER};
            border-radius: 6px;
        }}
        QLabel#tfName {{
            color: {TEXT2};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QLabel#tfDir {{
            font-size: 13px;
            font-weight: 800;
        }}

        /* ── Divider ── */
        QFrame#divider {{
            color: {BORDER};
            background: {BORDER};
            border: none;
            margin: 1px 0;
        }}

        /* ── Log ── */
        QTextEdit#logView {{
            background: {PANEL};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 8px;
            font-family: "Consolas", "Courier New", monospace;
            font-size: 12px;
            padding: 10px;
            selection-background-color: #263448;
        }}
        QTextEdit#logView:disabled {{
            color: {TEXT2};
            background: {CARD};
        }}

        /* ── Settings button ── */
        QPushButton#settingsBtn {{
            background: {CARD};
            color: {TEXT2};
            border: 1px solid {BORDER};
            border-radius: 6px;
            font-size: 13px;
            font-weight: 700;
            padding: 7px 14px;
        }}
        QPushButton#settingsBtn:hover {{ border-color: {PURPLE}; color: {PURPLE}; }}

        /* ── Account panel ── */
        QLabel#acctValue {{
            color: {TEXT};
            font-size: 18px;
            font-weight: 800;
            font-family: "Consolas", "Courier New", monospace;
        }}
        QLabel#acctSub {{
            color: {TEXT2};
            font-size: 12px;
        }}
        QPushButton#longOrderBtn {{
            background: {GREEN_DIM};
            color: {GREEN};
            border: 1px solid {GREEN};
            border-radius: 6px;
            font-size: 12px;
            font-weight: 800;
            padding: 5px 10px;
        }}
        QPushButton#longOrderBtn:hover {{ background: #174a28; }}
        QPushButton#longOrderBtn:disabled {{
            color: {TEXT2}; border-color: {BORDER}; background: {CARD};
        }}
        QPushButton#shortOrderBtn {{
            background: {RED_DIM};
            color: {RED};
            border: 1px solid {RED};
            border-radius: 6px;
            font-size: 12px;
            font-weight: 800;
            padding: 5px 10px;
        }}
        QPushButton#shortOrderBtn:hover {{ background: #4a1414; }}
        QPushButton#shortOrderBtn:disabled {{
            color: {TEXT2}; border-color: {BORDER}; background: {CARD};
        }}
        QPushButton#closeOrderBtn {{
            background: {YELLOW_DIM};
            color: {YELLOW};
            border: 1px solid {YELLOW};
            border-radius: 6px;
            font-size: 12px;
            font-weight: 800;
            padding: 5px 10px;
        }}
        QPushButton#closeOrderBtn:hover {{ background: #4a3800; }}
        QPushButton#closeOrderBtn:disabled {{
            color: {TEXT2}; border-color: {BORDER}; background: {CARD};
        }}
        QDoubleSpinBox#acctSpin {{
            background: {CARD};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 5px;
            padding: 5px 8px;
            font-size: 13px;
            selection-background-color: {BLUE_DIM};
        }}
        QDoubleSpinBox#acctSpin:focus {{ border-color: {BLUE}; }}
        QDoubleSpinBox#acctSpin::up-button,
        QDoubleSpinBox#acctSpin::down-button {{
            background: {PANEL};
            border-left: 1px solid {BORDER};
            width: 16px;
        }}
        QDoubleSpinBox#acctSpin::up-button:hover,
        QDoubleSpinBox#acctSpin::down-button:hover {{
            background: {BLUE_DIM};
        }}
        QCheckBox#autoChk {{
            color: {TEXT2};
            font-size: 12px;
            font-weight: 700;
            spacing: 6px;
        }}
        QCheckBox#autoChk::indicator {{
            width: 15px;
            height: 15px;
            border: 1px solid {BORDER};
            border-radius: 3px;
            background: {CARD};
        }}
        QCheckBox#autoChk::indicator:checked {{
            background: {GREEN};
            border-color: {GREEN};
        }}
        QCheckBox#autoChk:checked {{ color: {GREEN}; font-weight: 800; }}

        /* ── Tab widget ── */
        QTabWidget#bottomTabs::pane {{
            border: 1px solid {BORDER};
            border-radius: 0 8px 8px 8px;
            background: {PANEL};
            top: -1px;
        }}
        QTabWidget#bottomTabs QWidget {{
            color: {TEXT};
        }}
        QTabBar::tab {{
            background: {CARD};
            color: {TEXT2};
            border: 1px solid {BORDER};
            border-bottom: none;
            padding: 6px 16px;
            font-size: 12px;
            font-weight: 700;
        }}
        QTabBar::tab:selected {{
            background: {PANEL};
            color: {TEXT};
            border-bottom: 1px solid {PANEL};
        }}
        QTabBar::tab:hover {{
            color: {BLUE};
        }}

        /* ── Trade table ── */
        QTableWidget#tradeTable {{
            background: {PANEL};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 8px;
            gridline-color: {BORDER};
            font-family: "Consolas", "Courier New", monospace;
            font-size: 12px;
            alternate-background-color: {CARD};
            selection-background-color: {BLUE_DIM};
            selection-color: {TEXT};
        }}
        QTableWidget#tradeTable::viewport {{
            background: {PANEL};
            border-radius: 8px;
        }}
        QHeaderView {{
            background: {CARD};
            color: {TEXT2};
        }}
        QTableWidget#tradeTable QHeaderView::section {{
            background: {CARD};
            color: {TEXT2};
            border: 0;
            border-bottom: 1px solid {BORDER};
            border-right: 1px solid {BORDER};
            padding: 5px 8px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
        }}
        QTableCornerButton::section {{
            background: {CARD};
            border: 0;
            border-bottom: 1px solid {BORDER};
            border-right: 1px solid {BORDER};
        }}
        QTableWidget#tradeTable::item {{
            padding: 4px 8px;
            border: none;
        }}
        QTableWidget#tradeTable::item:selected {{
            background: {BLUE_DIM};
            color: {TEXT};
        }}

        /* ── Mode combo ── */
        QComboBox#modeCombo {{
            background: {CARD};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 5px;
            padding: 5px 24px 5px 8px;
            font-size: 12px;
            font-weight: 700;
        }}
        QComboBox#modeCombo:hover {{
            border-color: {BLUE};
        }}
        QComboBox#modeCombo::drop-down {{
            border: none;
            width: 22px;
            background: {PANEL};
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
        }}
        QComboBox#modeCombo QAbstractItemView {{
            background: {CARD};
            color: {TEXT};
            border: 1px solid {BORDER};
            selection-background-color: {BLUE_DIM};
            outline: 0;
        }}

        /* ── Emergency stop ── */
        QPushButton#emergencyBtn {{
            background: {RED_DIM};
            color: {RED};
            border: 1px solid {RED};
            border-radius: 6px;
            font-size: 12px;
            font-weight: 900;
            padding: 7px 10px;
        }}
        QPushButton#emergencyBtn:hover {{ background: #5c1010; }}

        /* ── DateEdit ── */
        QDateEdit#acctSpin {{
            background: {CARD};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 5px;
            padding: 5px 24px 5px 8px;
            font-size: 12px;
            selection-background-color: {BLUE_DIM};
        }}
        QDateEdit#acctSpin:focus {{ border-color: {BLUE}; }}
        QDateEdit#acctSpin::drop-down {{
            border: none;
            width: 22px;
            background: {PANEL};
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
        }}
        QCalendarWidget QWidget {{
            background: {PANEL};
            color: {TEXT};
        }}
        QCalendarWidget QToolButton {{
            background: {CARD};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 5px;
            padding: 4px 8px;
        }}
        QCalendarWidget QMenu {{
            background: {CARD};
            color: {TEXT};
            border: 1px solid {BORDER};
        }}
        QCalendarWidget QSpinBox {{
            background: {CARD};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 2px 6px;
        }}
        QCalendarWidget QAbstractItemView {{
            background: {PANEL};
            color: {TEXT};
            selection-background-color: {BLUE_DIM};
            selection-color: {TEXT};
            outline: 0;
        }}
        QSpinBox#acctSpin {{
            background: {CARD};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 5px;
            padding: 5px 8px;
            font-size: 13px;
            selection-background-color: {BLUE_DIM};
        }}
        QSpinBox#acctSpin:focus {{ border-color: {BLUE}; }}
        QSpinBox#acctSpin::up-button,
        QSpinBox#acctSpin::down-button {{
            background: {PANEL};
            border-left: 1px solid {BORDER};
            width: 16px;
        }}
        QSpinBox#acctSpin::up-button:hover,
        QSpinBox#acctSpin::down-button:hover {{
            background: {BLUE_DIM};
        }}

        /* ── Scrollbar ── */
        QScrollBar:vertical {{
            background: {PANEL};
            width: 7px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {BORDER};
            border-radius: 3px;
            min-height: 20px;
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{ height: 0; }}
        """


# ── Entry ──────────────────────────────────────────────────────────────────────

def run_gui():
    app = QApplication([])
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 9))
    win = TradingMainWindow()
    win.show()
    app.exec()
