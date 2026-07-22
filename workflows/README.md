# workflows/

Кладіть сюди YAML-файли Pointee v2 воркфлоу (`*.yaml`). Кожен файл, доданий
у цю папку, автоматично перевіряється тестами з
`tests/test_pointee_workflows.py`, а перед комітом його варто прогнати через
субагента `pointee-validator`.

## Очікувана структура файлу

```yaml
name: contract_review          # унікальна назва воркфлоу
description: ...                # опційно
attachments:
  count: 2                      # скільки слотів вкладень доступно (attachment0..attachmentN-1)
states:
  extract_terms:
    type: llm_extraction        # тип стану; для LLM-екстракції timeout обов'язковий
    call: pointee.ai.tool       # білтін, який виконує стан
    timeout:
      startToClose: 60s         # обов'язково для type: llm_extraction
    input:
      document: $.data.attachments.attachment0   # шляхи до даних лише через $.data.
      instructions: $.data.instructions
    transitions:
      - to: review_terms
      - to: notify_failure
        on: failure
  review_terms:
    type: approval
    call: pointee.approval.request
    on_approve: send_confirmation
    on_reject: notify_failure
  send_confirmation:
    type: action
    call: pointee.email.call
    transitions:
      - to: end
  notify_failure:
    type: action
    call: pointee.form.request
    transitions:
      - to: end
  end:
    type: terminal
```

## Правила v2, які перевіряють тести

1. Файл — валідний YAML і парситься без помилок.
2. Усі шляхи до даних (рядки, що починаються з `$.`) повинні починатися саме
   з `$.data.` (не `$.prop` чи будь-що інше).
3. Кожен стан з `type: llm_extraction` має мати `timeout.startToClose`.
4. Усі посилання на `attachmentN` мають потрапляти в діапазон, оголошений у
   `attachments.count`.
5. Усі переходи (`transitions[].to`, `on_success`, `on_failure`,
   `on_approve`, `on_reject`, `next`, `default`) вказують на існуючі стани —
   висячих переходів немає.
6. Поле `call` кожного стану — лише один із білтінів:
   `pointee.ai.tool`, `pointee.agent.run`, `pointee.form.request`,
   `pointee.approval.request`, `pointee.email.call`, `pointee.code.run`.

Ці автотести ловлять лише формальні/структурні помилки. Семантичне рев'ю
(логіка переходів, обробка помилок, дублікати станів тощо) виконує субагент
`pointee-validator` — викликайте його перед комітом змін у цій папці.
