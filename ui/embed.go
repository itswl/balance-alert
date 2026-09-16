// Package ui 把打包好的前端产物嵌进二进制。
//
// 产物提交进仓库：这样 go build ./... 和 go install 不需要先装 Node 也能得到一个
// 完整可用的程序。重新构建用 npm --prefix ui run build。
package ui

import (
	"embed"
	"errors"
	"io/fs"
)

//go:embed dist
var dist embed.FS

// ErrNotBuilt 表示 dist 里只有占位文件，前端还没真正构建过。
var ErrNotBuilt = errors.New("前端产物未构建，请先执行 npm --prefix ui run build")

// Assets 返回前端产物的文件系统根。
func Assets() (fs.FS, error) {
	sub, err := fs.Sub(dist, "dist")
	if err != nil {
		return nil, err
	}
	if _, err := fs.Stat(sub, "index.html"); err != nil {
		return nil, ErrNotBuilt
	}
	return sub, nil
}
