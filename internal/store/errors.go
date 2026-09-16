package store

import "errors"

// ErrDisabled 表示这次写入需要数据库动态配置，但数据库没开。
// HTTP 层把它翻译成 503。
var ErrDisabled = errors.New("数据库未启用，无法写入动态配置")
