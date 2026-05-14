import os
import requests
import pandas as pd
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

def fetch_nfci():
    """FRED에서 최신 NFCI 데이터를 가져옵니다."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCI"
    try:
        df = pd.read_csv(url)
        df = df.dropna()
        latest_row = df.iloc[-1]
        date = latest_row['observation_date']
        value = float(latest_row['NFCI'])
        return date, value
    except Exception as e:
        print(f"NFCI 데이터 조회 중 오류 발생: {e}")
        return None, None

def analyze_and_notify(date, value):
    """NFCI 값을 분석하고 항상 디스코드로 현재 상황을 알림 전송합니다."""
    
    # 기본 상태 메시지
    message = (
        f"📊 **[주간 NFCI 업데이트]**\n"
        f"**기준일:** {date}\n"
        f"**현재 NFCI:** `{value:.2f}`\n\n"
    )
    
    if value >= -0.1:
        message += (
            f"🚨 **증시 저점은 기회야!! (금융 긴축 심화)** 🚨\n"
            f"현재 NFCI가 -0.1 이상으로 치솟았습니다.\n\n"
            f"**💡 역사적 그 당시 상황 돌아보기:**\n"
            f"• **2000년 닷컴버블 붕괴:** 금리 인상과 함께 이익이 없는 IT 기업들의 거품이 터지며 자금이 순식간에 말라붙었습니다.\n"
            f"• **2008년 금융위기:** 서브프라임 모기지 사태로 초대형 은행(리먼 브라더스)이 파산하며, '누가 언제 망할지 모른다'는 극도의 신용 경색 공포가 지배했습니다.\n"
            f"• **2020년 코로나 발발:** 전 세계 경제가 셧다운되면서 모든 자산(주식, 금, 채권 가릴 것 없이)이 현금 확보를 위해 투매되는 패닉 셀링이 일어났습니다.\n"
            f"• **2022년 금리 인상기 초입:** 40년 만의 최악의 인플레이션을 잡기 위해 연준이 자이언트 스텝을 밟으며 시장의 유동성을 강제로 흡수하기 시작했습니다.\n\n"
            f"대중은 이처럼 '세상이 끝날 것 같은 공포'에 질려 주식을 던지고 자금줄이 마르는 시기지만, 반대로 생각하면 **자산 가격이 충분히 싸진 훌륭한 매수 기회(저점)**일 수 있습니다.\n"
            f"공포를 매수할 준비를 해보세요!"
        )
    elif value <= -0.6:
        message += (
            f"⚠️ **고점은 위험해 이제 슬슬 주식들을 정리하는게 좋을거같아!! (금융 과열/버블 경계)** ⚠️\n"
            f"현재 NFCI가 -0.6 이하로 매우 낮아, 시장에 유동성이 극도로 넘쳐나고 있습니다.\n\n"
            f"**💡 역사적 그 당시 상황 돌아보기:**\n"
            f"• **2017년 말 (볼마겟돈 직전):** '골디락스(뜨겁지도 차갑지도 않은 완벽한 경제)'라는 환희 속에서 변동성(VIX)을 매도하는 상품이 유행할 정도로 시장이 지나치게 안일했습니다. 직후 변동성이 폭발하며 큰 하락을 맞았습니다.\n"
            f"• **2021년 하반기:** 제로금리와 무제한 양적완화로 돈이 복사되던 시기였습니다. 밈 주식, 코인, NFT 등 자산 가치와 무관하게 '가즈아'를 외치며 빚을 내서 투자하던 비이성적 과열의 절정이었습니다.\n\n"
            f"극도의 완화 이후에는 필연적으로 인플레이션이나 버블 붕괴로 인한 '급격한 긴축'이 뒤따르며 큰 폭의 하락장이 발생하곤 했습니다.\n"
            f"환희에 취해 모두가 돈을 번다고 자랑할 때가 가장 위험합니다. 비이성적 과열 상태일 수 있으므로 **이제 슬슬 수익을 실현하고 현금 비중을 늘리는 것**이 좋습니다."
        )
    else:
        message += (
            f"✅ **현재 증시는 안정(정상) 구간에 있습니다.**\n"
            f"NFCI가 -0.6과 -0.1 사이에 머물며 극단적인 긴축이나 완화 없이 원활한 흐름을 보이고 있습니다.\n"
            f"기존 투자 전략을 유지하며 시장 상황을 모니터링하세요."
        )

    print(message)
    if DISCORD_WEBHOOK_URL:
        try:
            payload = {"content": message}
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            if response.status_code == 204:
                print("디스코드 알림 전송 완료.")
            else:
                print(f"디스코드 전송 실패: {response.status_code}")
        except Exception as e:
            print(f"디스코드 웹훅 전송 중 오류 발생: {e}")
    else:
        print("디스코드 웹훅 URL이 설정되지 않아 메시지를 전송하지 않았습니다.")

if __name__ == "__main__":
    date, value = fetch_nfci()
    if date and value is not None:
        analyze_and_notify(date, value)
