import asyncio
from telegram import Bot 
from pathlib import Path
'''
    Prerequisites: python-telegram-bot
    Install using: pip install python-telegram-bot
'''
'''
    To use:
    Import this function using "from killcambot.py import *"
    Call the function: send_video_to_subscribers("poop.mp4", "caption") 
    This function assumes all videos are stored in the same folder as the script 
'''

async def _async_send_video_core(video_filename: str, caption: str = None):
    # Configuration stuff
    TELEGRAM_BOT_TOKEN = "7954230057:AAHpn8-TH2Ftn45yBweE3zGQ93PNPTCt56s"
    VIDEO_FOLDER = Path(__file__).resolve().parent 
    # VIDEO_FOLDER = Path('C:\\example\\'))
    # Use the option above if you want to specify an absolute path


    SUBSCRIBER_CHAT_IDS = [
        '-1003472830495', # join this group using https://t.me/+iwu9Y1COVo40NDU1
        # you can add more to this list
    ]

    # Actual shit starts below
    video_path = VIDEO_FOLDER / video_filename
    
    if not video_path.is_file():
        print(f"Are you sure the video is at: {video_path}")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    print(f"Uploading video '{video_filename}'")

    # Open the video file once for reading
    with open(video_path, 'rb') as video_file:
        for chat_id in SUBSCRIBER_CHAT_IDS:
            try:
                video_file.seek(0)
                
                await bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    caption=caption,
                    read_timeout=60, # Increase timeout for large files
                    write_timeout=60, # as above
                )
                print(f"Successfully sent {video_filename}")
                await asyncio.sleep(1) 

            except Exception as e:
                print(f"Failed to send to chat ID {chat_id}. Error: {e}")
                
    print("Video sending process complete.")


def send_video_to_subscribers(video_filename: str, caption: str = None):
    print("[STATUS] Delivering video to your Telegram channel")
    try:
        asyncio.run(_async_send_video_core(video_filename, caption))
    except Exception as e:
        print(f"{e}")

