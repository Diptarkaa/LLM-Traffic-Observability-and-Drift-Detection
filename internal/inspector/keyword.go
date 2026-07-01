package inspector

import (
	"fmt"
	"strings"
)

// KeywordInspector checks traffic for a specific blocked string.
type KeywordInspector struct {
	BlockedKeyword string
	WarnKeyword    string
}

// NewKeywordInspector creates a new KeywordInspector.
func NewKeywordInspector(blockedKeyword string, warnKeyword string) *KeywordInspector {
	return &KeywordInspector{
		BlockedKeyword: strings.ToLower(blockedKeyword),
		WarnKeyword:    strings.ToLower(warnKeyword),
	}
}

// Inspect checks if the payload content has the blocked keyword.
func (k *KeywordInspector) Inspect(pType PayloadType, content string) Result {
	// Perform a case insensitive check.
	if strings.Contains(strings.ToLower(content), k.BlockedKeyword) {
		return Result{
			Type:    Block,
			Body:    "Blocked by AAPH Guardrail: Policy Violation.",
			Headers: []string{fmt.Sprintf("akamai-x-llmg-deny-rule: keyword '%s' detected", k.BlockedKeyword)},
		}
	}

	// Perform a case insensitive check.
	if strings.Contains(strings.ToLower(content), k.WarnKeyword) {
		return Result{
			Type:    Warn,
			Headers: []string{fmt.Sprintf("akamai-x-llmg-warn-rule: keyword '%s' detected", k.WarnKeyword)},
		}
	}

	return Result{Type: Safe}
}
