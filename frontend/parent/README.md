# ADEM for Parents

Parents sign up (email or Google), add their children, and set timed CBSE practice exams at home. The child
writes on paper, the parent uploads the answer sheet, and ADEM marks it. One credit marks one answer sheet;
new accounts get 10 free credits. React + TypeScript + Vite + Tailwind.

```bash
npm install
npm run dev        # http://localhost:5175, proxies /api to the backend on :8000
npm run build      # type-check + production build
```

Sign-in uses the `parent` portal. Without SMTP on the backend, the signup confirmation link is in the
backend `data/outbox/` folder.
