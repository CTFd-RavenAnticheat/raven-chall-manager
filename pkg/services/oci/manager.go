package oci

import (
	"sync"

	"go.uber.org/zap"
)

type Manager struct {
	Logger *zap.Logger

	locks    *sync.Map
	digCache map[string]*cacheEntry

	insecure           bool
	username, password string

	cacheOverride string
}

func NewManager(
	logger *zap.Logger,
	insecure bool,
	username, password string,
	cacheOverride string,
) *Manager {
	return &Manager{
		Logger:        logger,
		locks:         &sync.Map{},
		digCache:      map[string]*cacheEntry{},
		insecure:      insecure,
		username:      username,
		password:      password,
		cacheOverride: cacheOverride,
	}
}
