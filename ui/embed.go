// Package ui embeds the built frontend assets into the binary.
//
// The generated assets are committed so go build ./... and go install work without Node.
// Rebuild them with npm --prefix ui run build.
package ui

import (
	"embed"
	"errors"
	"io/fs"
)

//go:embed dist
var dist embed.FS

// ErrNotBuilt indicates that dist contains only placeholder assets.
var ErrNotBuilt = errors.New("frontend assets are not built; run npm --prefix ui run build first")

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
