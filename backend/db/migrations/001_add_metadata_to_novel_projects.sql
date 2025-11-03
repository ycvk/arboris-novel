-- 为 novel_projects 表添加 metadata 字段
-- 用于存储蓝图草稿等临时数据

-- MySQL
ALTER TABLE novel_projects ADD COLUMN metadata JSON NULL AFTER status;

-- SQLite (如果使用 SQLite，请使用以下语句)
-- ALTER TABLE novel_projects ADD COLUMN metadata TEXT NULL;

