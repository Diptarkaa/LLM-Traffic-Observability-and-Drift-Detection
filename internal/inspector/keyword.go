package inspector

import "strings"

// KeywordInspector checks traffic for a specific blocked string.
type KeywordInspector struct {
	BlockedKeyword string
}

// NewKeywordInspector creates a new KeywordInspector.
func NewKeywordInspector(keyword string) *KeywordInspector {
	return &KeywordInspector{BlockedKeyword: strings.ToLower(keyword)}
}

// Inspect checks if the payload content has the blocked keyword.
func (k *KeywordInspector) Inspect(pType PayloadType, content string) Result {
	// Perform a case insensitive check.
	if strings.Contains(strings.ToLower(content), k.BlockedKeyword) {
		return Result{
			IsBlocked: true,
			Message:   "Blocked by AAPH Guardrail: Policy Violation.",
		}
	}

	return Result{IsBlocked: false}
}
