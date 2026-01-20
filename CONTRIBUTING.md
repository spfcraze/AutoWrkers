# Contributing to UltraClaude

Thank you for your interest in contributing to UltraClaude! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)

---

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment. Please:

- Be respectful and considerate in all interactions
- Welcome newcomers and help them get started
- Focus on constructive feedback
- Accept responsibility for mistakes and learn from them

---

## Getting Started

### Finding Issues to Work On

1. Check the [Issues](https://github.com/yourusername/ultraclaude/issues) page
2. Look for issues labeled:
   - `good first issue` - Great for newcomers
   - `help wanted` - Looking for contributors
   - `bug` - Bug fixes
   - `enhancement` - New features

3. Comment on the issue to express interest before starting work

### Reporting Bugs

When reporting bugs, please include:

1. **Environment**: OS, Python version, browser
2. **Steps to Reproduce**: Detailed steps to trigger the bug
3. **Expected Behavior**: What should happen
4. **Actual Behavior**: What actually happens
5. **Logs/Screenshots**: Any relevant output

Use this template:

```markdown
## Bug Report

**Environment:**
- OS: Ubuntu 22.04
- Python: 3.11.0
- Browser: Chrome 120

**Steps to Reproduce:**
1. Go to Projects page
2. Click "New Project"
3. ...

**Expected Behavior:**
The project should be created.

**Actual Behavior:**
Error message appears: "..."

**Logs:**
```
paste logs here
```
```

### Suggesting Features

Feature requests are welcome! Please:

1. Check existing issues to avoid duplicates
2. Describe the use case clearly
3. Explain how it benefits users
4. Consider implementation complexity

---

## Development Setup

### Prerequisites

- Python 3.9+
- Node.js 18+ (for Claude Code CLI)
- Git
- tmux

### Setting Up Development Environment

```bash
# Fork the repository on GitHub

# Clone your fork
git clone https://github.com/YOUR_USERNAME/ultraclaude.git
cd ultraclaude

# Add upstream remote
git remote add upstream https://github.com/yourusername/ultraclaude.git

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-asyncio black flake8 mypy

# Start development server
python -m src.server
```

### Project Structure

```
ultraclaude/
├── src/                    # Python source code
│   ├── server.py          # FastAPI application
│   ├── session_manager.py # Session management
│   ├── models.py          # Data models
│   ├── automation.py      # GitHub automation
│   ├── github_client.py   # GitHub API client
│   ├── llm_provider.py    # LLM abstraction
│   ├── agentic_runner.py  # Local LLM agent
│   └── tools.py           # Agentic tools
├── web/
│   ├── templates/         # HTML templates
│   └── static/            # CSS, JS assets
├── docs/                   # Documentation
├── tests/                  # Test files
└── data/                   # Runtime data (gitignored)
```

---

## Making Changes

### Branching Strategy

1. Create a feature branch from `main`:
   ```bash
   git checkout main
   git pull upstream main
   git checkout -b feature/your-feature-name
   ```

2. Branch naming conventions:
   - `feature/` - New features
   - `fix/` - Bug fixes
   - `docs/` - Documentation
   - `refactor/` - Code refactoring

### Commit Messages

Follow conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting (no code change)
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance

Examples:
```
feat(llm): add support for Anthropic Claude API
fix(session): resolve tmux output encoding issue
docs(readme): update installation instructions
```

### Keep Changes Focused

- One feature/fix per pull request
- Keep PRs reasonably sized (< 500 lines ideally)
- Split large changes into smaller PRs

---

## Pull Request Process

### Before Submitting

1. **Update your branch:**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run tests:**
   ```bash
   pytest tests/
   ```

3. **Check code style:**
   ```bash
   black --check src/
   flake8 src/
   ```

4. **Update documentation** if needed

### Submitting PR

1. Push your branch:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Open a Pull Request on GitHub

3. Fill out the PR template:
   ```markdown
   ## Summary
   Brief description of changes

   ## Changes
   - Change 1
   - Change 2

   ## Testing
   How to test these changes

   ## Screenshots
   (if applicable)

   ## Checklist
   - [ ] Tests pass
   - [ ] Code follows style guide
   - [ ] Documentation updated
   ```

### Review Process

1. Maintainers will review your PR
2. Address any feedback
3. Once approved, your PR will be merged

---

## Coding Standards

### Python Style

We follow PEP 8 with these tools:

- **Black** for formatting
- **Flake8** for linting
- **isort** for import sorting

```bash
# Format code
black src/

# Check style
flake8 src/

# Sort imports
isort src/
```

### Key Guidelines

1. **Type hints**: Use type hints for function signatures
   ```python
   async def create_session(name: str, working_dir: str) -> Session:
   ```

2. **Docstrings**: Document public functions
   ```python
   def process_issue(issue: Issue) -> bool:
       """
       Process a GitHub issue and create a session.

       Args:
           issue: The GitHub issue to process

       Returns:
           True if session was created successfully
       """
   ```

3. **Error handling**: Use specific exceptions
   ```python
   try:
       result = await client.fetch()
   except GitHubAuthError:
       logger.error("Authentication failed")
       raise
   ```

### JavaScript Style

- Use modern ES6+ syntax
- Prefer `const` over `let`
- Use async/await for promises
- Keep functions small and focused

### HTML/CSS

- Use semantic HTML elements
- Follow BEM naming for CSS classes
- Keep styles in dedicated CSS files

---

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_session_manager.py

# Run with coverage
pytest --cov=src tests/

# Run async tests
pytest tests/ -v --asyncio-mode=auto
```

### Writing Tests

Place tests in the `tests/` directory:

```python
# tests/test_example.py
import pytest
from src.models import Project

def test_project_creation():
    project = Project(
        name="Test Project",
        github_repo="user/repo"
    )
    assert project.name == "Test Project"

@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

### Test Categories

- **Unit tests**: Test individual functions
- **Integration tests**: Test component interactions
- **E2E tests**: Test full workflows

---

## Documentation

### Updating Documentation

1. Keep README.md up to date
2. Document new features in `docs/`
3. Add docstrings to code
4. Update API documentation

### Documentation Style

- Use clear, concise language
- Include code examples
- Add screenshots for UI changes
- Keep formatting consistent

### Building Docs Locally

```bash
# If using mkdocs
pip install mkdocs
mkdocs serve
```

---

## Questions?

- Open an issue for questions
- Join discussions in existing issues
- Check existing documentation

Thank you for contributing to UltraClaude!
