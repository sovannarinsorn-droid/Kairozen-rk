# Kairozen Referral Bot — GitHub + Render Deploy

## ⚠️ សំខាន់មុនធ្វើអ្វីទាំងអស់
Token ចាស់ (`8881868407:...`) ធ្លាប់នៅក្នុងកូដដែលបាន upload ហើយ leak ហើយ។
**ទៅ @BotFather → `/revoke` token នោះ ហើយបង្កើត token ថ្មី** មុននឹង deploy។

## ជំហានទី 1 — Push ទៅ GitHub

```bash
cd kairozen_referral
git init
git add .
git commit -m "Kairozen Referral Bot v5"
git branch -M main
git remote add origin https://github.com/<your-username>/kairozen-referral-bot.git
git push -u origin main
```

(បង្កើត repo ថ្មីនៅ github.com/new សិន បើមិនទាន់មាន — ជ្រើស **Private** ព្រោះមានលទ្ធភាព leak secrets)

## ជំហានទី 2 — Deploy លើ Render

1. ចូល https://dashboard.render.com → **New +** → **Background Worker**
2. ភ្ជាប់ GitHub repo ដែល push រួច
3. Render នឹងអាន `render.yaml` ដោយស្វ័យប្រវត្តិ (Build/Start command កំណត់រួចរាល់)
4. ក្នុង **Environment** tab, បន្ថែម Environment Variables ទាំងនេះ៖

   | Key | Value |
   |---|---|
   | `BOT_TOKEN` | token ថ្មីពី @BotFather |
   | `ADMIN_ID` | `8266854899` (ឬ id admin ថ្មី) |
   | `CHANNEL_USERNAME` | `@kairozen_store3` |
   | `CHANNEL_URL` | `https://t.me/kairozen_store3` |

5. ចុច **Create Background Worker** → រង់ចាំ build ចប់

## ⚠️ ចំណាំពី db.json (សំខាន់)

Render free tier **disk មិន persistent** — ពេល redeploy ឬ restart, `db.json` (សមតុល្យ user, referrals, ប្រវត្តិ) **នឹងបាត់ទាំងអស់**។

ជម្រើសដោះស្រាយ៖
- **រហ័ស**: Render → Disks → បន្ថែម Persistent Disk (មិន free ទេ, ចាប់ពី $0.25/GB/ខែ) mount ត្រង់ `/opt/render/project/src/data` ហើយប្តូរ `DB_FILE=/opt/render/project/src/data/db.json`
- **ល្អជាង រយៈពេលវែង**: ប្តូរទៅប្រើ database ក្រៅ (Render PostgreSQL free tier, ឬ Supabase/MongoDB Atlas free tier)

បើមិនដោះស្រាយរឿងនេះ បើ redeploy ម្តងលុយ user ទាំងអស់នឹងលុបចោល។

## Files ក្នុង repo នេះ
- `bot.py` — កូដ bot (config ទាំងអស់អានពី env vars ហើយ)
- `requirements.txt`
- `render.yaml` — Render service config
- `.gitignore` — កុំឲ្យ db.json/token ចូល git
