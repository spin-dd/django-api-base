# django-api-base

- Graphene-Django
- Django REST Framework

## 保存時のトランザクション

`BaseModelSerializer.create()` / `update()` は、親の保存から入れ子の子の検証・保存までを
1つのトランザクションで実行します。子の検証や保存に失敗すると、親と、それまでに保存した子の
変更をすべて巻き戻します。`ATOMIC_REQUESTS` の設定は不要です。

対象 DB は親またはバッチ対象のモデルの `router.db_for_write()` で選び、単発の更新では
`instance` も hint として渡します。親と子が別々の DB に保存される場合は、全体を一括で
巻き戻すことはできません。

`BaseModelViewSet.create_batch()` / `update_batch()` もリクエスト全体を1つのトランザクションで
処理し、後続レコードの失敗時は先に処理したレコードの変更も巻き戻します。ViewSet を通さず
`many=True` のシリアライザを直接保存する場合や、バッチ処理を独自実装する場合は、
呼び出し側で全体を `transaction.atomic()` に含めてください。

一括作成・一括更新では、各親に渡した入れ子の子データをそれぞれの親に保存します。
ある親で子データを省略したり空の配列を渡したりしても、別の親の子データを使うことはありません。
空の配列は既存の子を削除する指定ではありません。

バッチは `perform_create()` / `perform_update()` までトランザクションに含みますが、単発は
`serializer.save()` 内の親と子の保存が対象なので、利用側で `perform_create()` / `perform_update()`
を上書きして保存後に別の書き込みをする場合は、利用側で全体を `transaction.atomic()` に含めてください。

保存後のシグナルはトランザクション内で実行されます。メール送信などの外部への処理は、
`transaction.on_commit()` で保存の確定後に実行してください。`default` 以外の DB を使う場合は、
呼び出し側の `transaction.atomic()` / `transaction.on_commit()` にも対象 DB の `using` を指定してください。
