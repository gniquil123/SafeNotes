"""数据库层测试：CRUD、筛选、回收站、历史版本、序列化往返。"""
import copy

from app.core.database import Database
from app.core.models import Entry, ImageItem, now_iso


def make_db(n=3):
    db = Database.empty()
    for i in range(n):
        e = Entry.new("password", category="工作" if i % 2 == 0 else "个人")
        e.title = f"条目{i}"
        e.fields["username"] = f"user{i}@x.com"
        db.insert(e)
    return db


def test_visible_filter_and_search():
    db = make_db(4)
    assert len(db.visible()) == 4
    assert len(db.visible("工作")) == 2
    assert len(db.visible("个人")) == 2
    assert len(db.visible("trash")) == 0
    assert len(db.visible(search="user3")) == 1
    assert len(db.visible(search="条目")) == 4
    assert len(db.visible(search="不存在")) == 0
    # 搜索应命中标题 / 账号 / 分类
    assert db.visible(search="工作")[0].category == "工作"


def test_visible_sorted_by_updated():
    db = make_db(3)
    db.entries[2].updated_at = "2099-01-01T00:00:00"
    assert db.visible()[0].id == db.entries[2].id


def test_soft_delete_and_trash():
    db = make_db(3)
    target = db.entries[0]
    db.soft_delete(target.id)
    assert len(db.visible()) == 2
    assert len(db.visible("trash")) == 1
    assert db.visible("trash")[0].deleted_at is not None
    total, per, trash = db.counts()
    assert (total, trash) == (2, 1)
    db.undelete(target.id)
    assert len(db.visible()) == 3


def test_purge_and_restore():
    db = make_db(3)
    ids = [db.entries[0].id, db.entries[2].id]
    removed = db.purge(ids)
    assert len(db.entries) == 1
    assert all(e.id not in ids for e in db.entries)
    db.restore_purged(removed)
    assert len(db.entries) == 3
    assert {e.id for e in db.entries} == set(ids) | {db.entries[1].id}


def test_history_push_and_limit():
    db = make_db(1)
    e = db.entries[0]
    db.settings["history_keep"] = 3
    e.title = "v1"
    e.history = db.push_history(e, "编辑保存")
    e.title = "v2"
    e.history = db.push_history(e, "编辑保存")
    e.title = "v3"
    e.history = db.push_history(e, "编辑保存")
    e.title = "v4"
    e.history = db.push_history(e, "编辑保存")
    assert len(e.history) == 3
    assert [h.snap["title"] for h in e.history] == ["v4", "v3", "v2"]   # 最新在前，超限丢最旧


def test_restore_history():
    db = make_db(1)
    e = db.entries[0]
    e.title, e.fields["password"] = "旧标题", "旧密码"
    e.history = db.push_history(e, "编辑保存")
    e.title, e.fields["password"] = "新标题", "新密码"

    ne = db.restore_history(e.id, 0)          # 恢复索引 0（最新快照）
    assert ne is not None
    total = len(e.history)                    # 恢复目标版本号 = total - 0
    assert ne.title == "旧标题" and ne.fields["password"] == "旧密码"
    assert len(ne.history) == 2               # 恢复前自动快照"新标题" + 原有的 1 条历史
    assert ne.history[0].snap["title"] == "新标题"
    assert ne.history[1].snap["title"] == "旧标题"
    assert "恢复第 1 版" in ne.history[0].reason
    db.replace(ne)
    assert db.get(e.id).title == "旧标题"


def test_version_numbering():
    """最初版是第 1 版：索引 i 的版本号 = 总数 - i。"""
    db = make_db(1)
    e = db.entries[0]
    for i in range(4):
        e.title = f"t{i}"
        e.history = db.push_history(e, "编辑保存")
    total = len(e.history)
    assert total == 4
    # history[3] 是最初版（第 1 版）
    assert "第 1 版" not in e.history[3].reason   # reason 只是快照说明
    # 通过 restore_history 的 reason 验证编号
    ne = db.restore_history(e.id, 3)
    assert "恢复第 1 版" in ne.history[0].reason
    ne2 = db.restore_history(e.id, 1)
    assert "恢复第 3 版" in ne2.history[0].reason


def test_serialize_roundtrip():
    db = make_db(3)
    e = db.entries[0]
    e.fields["password"] = "p@ss"
    e.images.append(ImageItem(name="a.png", data="aGk="))
    e.history = db.push_history(e, "编辑保存")
    db.soft_delete(db.entries[1].id)
    db.settings["theme"] = "dark"

    d = db.to_dict()
    db2 = Database.from_dict(copy.deepcopy(d))
    assert len(db2.entries) == 3
    e2 = db2.get(e.id)
    assert e2.fields["password"] == "p@ss"
    assert e2.images[0].name == "a.png"
    assert len(e2.history) == 1
    assert e2.history[0].snap["fields"]["password"] == "p@ss"
    assert db2.get(db.entries[1].id).deleted is True
    assert db2.settings["theme"] == "dark"


def test_empty_fields_compat():
    """缺字段的旧数据自动补默认值。"""
    d = {"entries": [{"id": "a", "type": "password", "title": "t",
                      "category": "", "fields": {}}], "settings": {}}
    db = Database.from_dict(d)
    e = db.entries[0]
    assert e.category == "默认"
    assert set(e.fields) == {"username", "password", "url", "notes"}
