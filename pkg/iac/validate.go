package iac

import (
	"context"
	"crypto/rand"
	"encoding/hex"

	"time"

	"github.com/ctfer-io/chall-manager/global"
	errs "github.com/ctfer-io/chall-manager/pkg/errors"
	fsapi "github.com/ctfer-io/chall-manager/pkg/fs"
	"github.com/pulumi/pulumi/sdk/v3/go/auto"
	"go.uber.org/zap"
)

// Validate check the challenge scenario can preview without error (a basic check).
func Validate(ctx context.Context, fschall *fsapi.Challenge) error {
	// Track span of loading stack
	ctx, span := global.Tracer.Start(ctx, "validating-scenario")
	defer span.End()

	logger := global.Log().With(zap.String("scenario", fschall.Scenario))
	logger.Info(ctx, "loading stack for validation")
	start := time.Now()
	rand := randName()
	stack, err := LoadStack(ctx, fschall.Scenario, rand)
	if err != nil {
		return err
	}
	logger.Info(ctx, "stack loaded", zap.Duration("duration", time.Since(start)))
	if err := stack.pas.SetAllConfig(ctx, auto.ConfigMap{
		"identity": auto.ConfigValue{
			Value: rand,
		},
	}); err != nil {
		return &errs.ErrInternal{Sub: err}
	}
	logger.Info(ctx, "stack config set")
	if err := Additional(ctx, stack, fschall.Additional, nil); err != nil {
		return &errs.ErrInternal{Sub: err}
	}

	// Preview stack to ensure it build without error
	logger.Info(ctx, "previewing stack")
	pstart := time.Now()
	if _, err := stack.pas.Preview(ctx); err != nil {
		return &errs.ErrScenario{Sub: err}
	}
	logger.Info(ctx, "preview finished", zap.Duration("duration", time.Since(pstart)))

	return nil
}

func randName() string {
	b := make([]byte, 8)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
