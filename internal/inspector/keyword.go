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
func (k *KeywordInspector) Inspect(pType PayloadType, content string, ctx *StreamContext) Result {
	// Perform a case insensitive check.
	if strings.Contains(strings.ToLower(content), k.BlockedKeyword) {
		ctx.ResponseHeaders["akamai-x-llmg-deny-rule"] = fmt.Sprintf("keyword '%s' detected", k.BlockedKeyword)
		ctx.ResponseBody = "Blocked by AAPH Guardrail: Policy Violation."
		return Block
	}

	// Perform a case insensitive check.
	if strings.Contains(strings.ToLower(content), k.WarnKeyword) {
		header := fmt.Sprintf("keyword '%s' detected", k.WarnKeyword)
		ctx.ResponseHeaders["akamai-x-llmg-warn-rule"] = header
		ctx.RequestHeaders["akamai-x-llmg-warn-rule"] = header
		return Warn
	}

	return Safe
}
