# Daily Sales Routine

Goal: get at least one paid `¥20` trial order per day.

## Morning Setup

1. Open the admin dashboard: `http://127.0.0.1:8000/admin`.
2. Confirm today's revenue is below or above `¥20`.
3. Copy the daily outreach message from the admin dashboard.
4. Prepare a list of 20 prospects.

## Prospect List

Prioritize people who already post or should be posting short videos:

- Restaurants with recent photos but weak captions
- Beauty or nail shops posting finished-work photos
- Gyms and trainers with class videos
- Homestays, hotels, and local attractions
- Small ecommerce sellers with product photos
- Creators who post inconsistently

## Outreach Rule

Send the message to 20 prospects before changing the offer.

Track replies manually at first:

- Contacted
- Replied
- Submitted trial form
- Paid
- Delivered
- Upsold

## Payment Handling

The app records intent, not payment. Confirm payment manually through WeChat, Alipay, Stripe, PayPal, or any channel you already use.

After payment:

1. Open `/admin`.
2. Find the order.
3. Click `标记已付款`.
4. The dashboard should count the order toward today's `¥20` revenue goal.

## Delivery

For each paid order:

1. Use the material notes in the order.
2. Paste the notes into the creation console.
3. Complete guided prompts.
4. Generate topics.
5. Generate one script.
6. Send the customer:
   - 3 topic angles
   - 1 shootable script
   - 5 hooks
   - 1 filming note
7. Mark the order as delivered in `/admin`.

## Upsell

After delivery, send:

```text
这次是单次试跑。如果你觉得有用，我可以每周给你做一组内容包：
¥199/月：20 个选题 + 8 条脚本
¥499/月：60 个选题 + 20 条脚本 + 每周内容方向
你可以先用这条拍一版，看效果后再决定。
```

