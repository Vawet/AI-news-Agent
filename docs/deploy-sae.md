# Deploy the AI News Agent to Alibaba Cloud SAE

The cloud process runs one health endpoint, one scheduler, and one Feishu
long-connection client. Keep the SAE replica count at **one** so only one
scheduler is active.

## 1. Create a Feishu application bot

1. Create an enterprise self-built application in Feishu Open Platform.
2. Enable the bot capability.
3. Grant application permissions for receiving group `@bot` messages and
   sending messages as the bot (`im.message.receive_v1`).
4. Configure event subscription with **long connection** mode.
5. Publish the application version and add the bot to the target group.
6. Record the App ID, App Secret, and target group `chat_id`.

A custom-bot webhook cannot receive group mentions and cannot replace this
application.

## 2. Build and push the image

Build from the repository root and push to the target ACR namespace:

```bash
docker build -t <acr-registry>/<namespace>/ai-news-agent:<tag> .
docker push <acr-registry>/<namespace>/ai-news-agent:<tag>
```

Do not bake `.env`, tokens, SSH keys, or cloud credentials into the image.

## 3. Configure the SAE application

- Image: the ACR image above
- Container port: `8080`
- Health path: `/health`
- Replicas: `1`
- Minimum instances: `1`
- Restart policy: always
- Network: outbound internet for news sources and Feishu, plus network access
  to the configured internal AI Gateway endpoint

Configure these values as SAE secrets/environment variables:

```text
AI_GATEWAY_TOKEN
AI_GATEWAY_BASE_URL
AI_GATEWAY_BIZID=hunter
AI_GATEWAY_ABILITY_KEY=gcp-claude-sonnet-4-6

FEISHU_APP_ID
FEISHU_APP_SECRET
FEISHU_ALLOWED_CHAT_IDS
FEISHU_TARGET_CHAT_ID
FEISHU_TRIGGER_COOLDOWN_SECONDS=3600

OSS_ENDPOINT
OSS_RESOURCE_BUCKET
OSS_ACCESS_KEY_ID
OSS_ACCESS_KEY_SECRET
OSS_PREFIX=ai-news-agent
OSS_CUSTOM_DOMAIN

SERVICE_PORT=8080
```

`FEISHU_ALLOWED_CHAT_IDS` is a comma-separated allowlist. The scheduled result
is sent to `FEISHU_TARGET_CHAT_ID`.

The shared AI Gateway token is explicitly platform-funded for this internal
bot. Restrict it with the chat allowlist, single concurrency, and cooldown.
A dedicated service token remains preferable when the gateway supports one.

## 4. Verify

1. Confirm `GET /health` returns `ok: true` and `feishu_configured: true`.
2. Mention the bot in the allowlisted group.
3. Confirm the immediate acknowledgement appears.
4. Confirm a result card with an OSS link appears after the pipeline finishes.
5. Repeat the same event and verify no second model run is dispatched.
6. Verify the scheduler shows Wednesday and Sunday at 10:00
   `Asia/Shanghai`.
