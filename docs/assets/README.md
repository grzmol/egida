# Materiały do slajdów (A8 krok 5)

| Plik | Co to jest |
|---|---|
| `architecture.svg` / `architecture.png` | Diagram przepływu żądania z `docs/architecture.md` (mermaid), PNG 2400 px szerokości |
| `dashboard.png` | Zrzut `/dashboard` (1600×1000) po `make selftest` i kilku żądaniach demo |

Zrzut dashboardu z commita `85b0a19`; diagram z `docs/architecture.md` w commicie `7c6ea30` (etapy C03, C09, C22, feed sygnatur, telemetria).

## Jak powstały

```sh
# diagram: blok mermaid z docs/architecture.md zapisany do a.mmd
npx -y @mermaid-js/mermaid-cli -i a.mmd -o docs/assets/architecture.png --size 2400 -b white
npx -y @mermaid-js/mermaid-cli -i a.mmd -o docs/assets/architecture.svg -b white

# proxy na stubie upstreamu (127.0.0.1:11502 odpowiada stałym tekstem na
# /v1/chat/completions i "safe" na /api/generate), kopia config/policy.yaml z base_url na stub
CONTROL_LAYER_POLICY=/tmp/sa/policy.yaml CONTROL_LAYER_AUDIT=/tmp/sa/audit.jsonl \
CONTROL_LAYER_GUARD_URL=http://127.0.0.1:11502 \
  uv run uvicorn control_layer.app:create_app --factory --port 8102
make selftest TARGET=http://127.0.0.1:8102      # 184 passed, 56 skipped
# + żądania demo: PESEL (redact), injection, klucz AWS (block),
#   pickle base64 jako sk-sig-probe-agent (signatures), injection w tool result
# zrzut: headless Chromium, viewport 1600x1000, po 5 s, sips -Z 1600
```

## Uwagi

- Upstream to stub, nie prawdziwy model. Latencje z dashboardu (p50/p95 1/2 ms) i koszty
  **nie nadają się na slajdy**; prawdziwe liczby to benchmark Maciej D5 w
  `docs/tasks/maciej/README.md`.
- Żółty baner „Posture weakened: harmful_content, prompt_guard” wynika z maszyny bez modeli
  (brak ONNX Prompt Guard, brak guard modelu), nie z konfiguracji produkcyjnej.
- Liczby z tego przebiegu: 187 żądań, 94 block, 19 redact, 0 błędów kontroli i upstreamu,
  selftest 183 ✓ / 0 ✗ na dashboardzie.
