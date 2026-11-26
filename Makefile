BINDIR ?= $(HOME)/.local/bin
SRC := $(CURDIR)/prco.py
LINK := $(BINDIR)/prco
PYTEST ?= uvx pytest

.PHONY: help install uninstall test

help: ## Show this help
	@if [ -t 1 ]; then e=$$(printf '\033'); b="$$e[1m" c="$$e[36m" y="$$e[33m" r="$$e[0m"; fi; \
	printf "$${b}Usage:$${r} make $${c}<target>$${r} [BINDIR=$${y}$(BINDIR)$${r}] [PYTEST=$${y}$(PYTEST)$${r}]\n\n"; \
	grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z]+):.*## /\1\t/; '"s|BINDIR/prco|$${y}$(LINK)$${r}|g" | \
	while IFS="$$(printf '\t')" read -r t h; do printf "  $${c}%-10s$${r} %s\n" "$$t" "$$h"; done

install: ## Symlink prco.py as BINDIR/prco
	mkdir -p $(BINDIR)
	ln -sfn $(SRC) $(LINK)

uninstall: ## Remove BINDIR/prco if it links to this checkout
	@if [ "$$(readlink $(LINK))" = "$(SRC)" ]; then rm $(LINK) && echo "removed $(LINK)"; \
	elif [ -e $(LINK) ] || [ -L $(LINK) ]; then echo "$(LINK) is not a link to $(SRC); leaving it" >&2; exit 1; \
	fi

test: ## Run the test suite
	$(PYTEST) -q tests
