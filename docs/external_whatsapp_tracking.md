# External WhatsApp Tracking

## Purpose

The platform distinguishes between messages sent through controlled platform
channels and messages observed from supported external WhatsApp clients.

Controlled channels include:

- Platform APIs
- Odoo through platform APIs
- Authorized integrations

External channels include supported WhatsApp Business App / linked-device
activity exposed by Meta.

External activity is synchronized only when Meta exposes sufficient provider
data.

---

## Message Source

Externally observed WhatsApp messages are stored with:

```text
direction = outbound
source = whatsapp_external
status = sent