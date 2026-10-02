# django-api-base

- Graphene-Django
- Django REST Framework

## 保存時のトランザクション

`BaseModelSerializer.create()` / `update()` は、親の保存から入れ子の子の検証・保存までを
1つのトランザクションで実行します。子の検証や保存に失敗すると、親と、それまでに保存した子の
変更をすべて巻き戻します。`ATOMIC_REQUESTS` の設定は不要です。

`BaseModelViewSet.create_batch()` / `update_batch()` もリクエスト全体を1つのトランザクションで
処理し、後続レコードの失敗時は先に処理したレコードの変更も巻き戻します。ViewSet を通さず
`many=True` のシリアライザを直接保存する場合や、バッチ処理を独自実装する場合は、
呼び出し側で全体を `transaction.atomic()` に含めてください。

保存後のシグナルはトランザクション内で実行されます。メール送信などの外部への処理は、
`transaction.on_commit()` で保存の確定後に実行してください。
