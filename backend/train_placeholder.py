"""
Future training entry point.
Current project uses a rule-based TradingAIEngine first.
Later you can replace it with PyTorch / LightGBM model training here.
"""


def main():
    print("현재 버전은 규칙 기반 분석 엔진입니다.")
    print("다음 단계에서 6년치 DB를 학습하여 models/btcusdt_model.pth 또는 .pkl로 저장하면 됩니다.")


if __name__ == "__main__":
    main()
