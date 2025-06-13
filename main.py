import os, asyncio, re
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types
from aiogram import F
from aiogram.filters import CommandStart
from fastapi.middleware.cors import CORSMiddleware
from aiogram.types import FSInputFile
from io import BytesIO
import base64
import tempfile
from openai import OpenAI

# ---------- env & global ----------
load_dotenv()
BOT_TOKEN  = os.getenv("BOT_TOKEN")
ADMIN_ID   = int(os.getenv("ADMIN_ID"))
AI_URL     = os.getenv("AI_API_URL")
AI_KEY     = os.getenv("AI_API_KEY")  # ممکن است None باشد

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

# ---------- FastAPI ----------
app = FastAPI(title="Smart-Advisor back-end")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # یا ["http://127.0.0.1:5501"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Req(BaseModel):
    user_id: int          # آی‌دی تلگرامی کاربر
    product: str
    problems: list[str]
    extra_info: str = ""
    photos: list[str] = []   # فایل آیدی یا URL عکس

@app.post("/api/analyze")
async def analyze(req: Req):
    """Endpointی که مینی-اپ صدا می‌زند."""
    if AI_KEY:
        try:
            client = OpenAI(
                base_url=AI_URL.replace("/chat/completions", ""),
                api_key=AI_KEY
            )
            prompt = f"""
            محصول: {req.product}
            مشکلات: {', '.join(req.problems)}
            توضیحات: {req.extra_info}
            """
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "تو یک کارشناس کشاورزی هستی که فقط به زبان فارسی و دقیق جواب می‌ده و راهکارها را به صورت لیست بولت‌دار (•) بنویس."},
                        {"role": "user", "content": prompt}
                    ]
                )
            )
            data = response.choices[0].message.content

            # استخراج راهکارها از متن (خطوطی که با • یا - شروع می‌شوند)
            suggestions = re.findall(r"^[•\-]\s*(.+)$", data, re.MULTILINE)
            return {"success": True, "result": {"analysis": data, "suggestions": suggestions}}
        except Exception as e:
            await notify_admin(req, str(e))
    else:
        await notify_admin(req, "NO_API_KEY")
    return {"success": False}

# ---------- کمک-تابع ارسال به ادمین ----------
async def notify_admin(req: Req, err: str):
    caption = (
        f"📥 گزارش جدید کاربر\n"
        f"USER_ID:{req.user_id}\n"
        f"محصول: {req.product}\n"
        f"مشکلات: {', '.join(req.problems)}\n"
        f"توضیحات: {req.extra_info}\n"
        f"خطا/وضعیت API: {err}"
    )
    await bot.send_message(ADMIN_ID, caption)
    for p in req.photos:
        if p.startswith("data:"):
            # تبدیل base64 به فایل و ارسال با FSInputFile
            header, b64data = p.split(",", 1)
            img_bytes = base64.b64decode(b64data)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                tmp.write(img_bytes)
                tmp.flush()
                await bot.send_photo(ADMIN_ID, FSInputFile(tmp.name))
        else:
            await bot.send_photo(ADMIN_ID, p)

# ---------- هندلرهای بات ----------
@dp.message(CommandStart())
async def start(m: types.Message):
    await m.answer("سلام! درخواستت رو از طریق وب-اپ بفرست تا بررسی کنم.")

# ادمین ریپلای می‌کند → جواب به کاربر برگردد
@dp.message(F.reply_to_message & (F.from_user.id == ADMIN_ID))
async def admin_reply(m: types.Message):
    match = re.search(r"USER_ID:(\d+)", m.reply_to_message.text or "")
    if not match:
        await m.answer("آی‌دی کاربر پیدا نشد.")
        return
    tgt = int(match.group(1))
    await bot.send_message(tgt, f"👨‍🌾 پاسخ پشتیبان:\n{m.text}")
    await m.answer("✅ پاسخ ارسال شد.")

# ---------- اجرا ----------
async def main():
    # bot polling داخل یک تسک جدا اجرا می‌شود
    asyncio.create_task(dp.start_polling(bot))
    # uvicorn را جداگانه بالا نمی‌آوریم؛
    #   این فایل را با «uvicorn main:app --reload» اجرا کن
    # و ایونت‌لوپِ uvicorn همان لوپِ asyncio است.
    pass

if __name__ == "__main__":
    asyncio.run(main())
