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
	lowerContent := strings.ToLower(content)
	var bloackedKeyword, warnKeyword string

	switch pType {
	case RequestHeader:
		bloackedKeyword = fmt.Sprintf("%s-req-head", k.BlockedKeyword)
		warnKeyword = fmt.Sprintf("%s-req-head", k.WarnKeyword)
	case RequestBody:
		bloackedKeyword = fmt.Sprintf("%s-req-body", k.BlockedKeyword)
		warnKeyword = fmt.Sprintf("%s-req-body", k.WarnKeyword)
	case ResponseHeader:
		bloackedKeyword = fmt.Sprintf("%s-res-head", k.BlockedKeyword)
		warnKeyword = fmt.Sprintf("%s-res-head", k.WarnKeyword)
	case ResponseBody:
		bloackedKeyword = fmt.Sprintf("%s-server", k.BlockedKeyword)
		warnKeyword = fmt.Sprintf("%s-server", k.WarnKeyword)
	}

	// Perform a case insensitive check.
	if strings.Contains(lowerContent, bloackedKeyword) {
		ctx.ResponseHeaders["akamai-x-llmg-deny-rule"] = fmt.Sprintf("keyword '%s' detected", bloackedKeyword)
		ctx.ResponseBody = "Blocked by AAPH Guardrail: Policy Violation."
		return Block
	}

	// Perform a case insensitive check.
	if strings.Contains(lowerContent, warnKeyword) {
		header := fmt.Sprintf("keyword '%s' detected", warnKeyword)
		ctx.ResponseHeaders["akamai-x-llmg-warn-rule"] = header
		ctx.RequestHeaders["akamai-x-llmg-warn-rule"] = header
		return Warn
	}

	return Safe
}
