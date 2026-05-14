import os
import sys
from dotenv import load_dotenv

# Set encoding for Windows output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Call the logic directly from analyze_ichimoku
try:
    import analyze_ichimoku
    if __name__ == "__main__":
        print("Starting standalone Discord report...")
        analyze_ichimoku.send_to_discord()
except ImportError as e:
    print(f"Error loading analyze_ichimoku: {e}")