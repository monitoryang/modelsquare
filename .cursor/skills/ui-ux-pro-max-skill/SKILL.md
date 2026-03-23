---
name: ui-ux-pro-max-skill
description: Provides design intelligence for building professional UI/UX across multiple platforms (web, mobile, desktop). Use when asked to design interfaces, improve UX, create design systems, or build platform-specific UI components.
metadata:
  author: nextlevelbuilder
  version: "1.0.0"
  source: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
  note: |
    This file was scaffolded locally because raw.githubusercontent.com is
    unreachable in the current network environment. Replace with the original
    content once network access is restored:
      curl -fsSL https://raw.githubusercontent.com/nextlevelbuilder/ui-ux-pro-max-skill/main/SKILL.md \
        > .cursor/skills/ui-ux-pro-max-skill/SKILL.md
---

# UI/UX Pro Max Skill

This skill provides AI-powered design intelligence for building professional,
polished user interfaces and experiences across web, mobile, and desktop platforms.

## Activation

Trigger this skill when the user:
- Asks to design or redesign a UI component, page, or full application
- Requests UX review, critique, or improvement suggestions
- Wants a design system, component library, or style guide
- Needs platform-specific guidance (iOS, Android, Web, Desktop)
- Says "make it look better", "improve the design", "pro UI", "UX audit"

## Design Intelligence Framework

### 1. Context Discovery
Before producing any output, gather:
- **Platform**: Web (responsive/PWA), iOS, Android, Desktop (Electron/Tauri), or cross-platform
- **Audience**: Consumer, enterprise, developer tool, creative tool, etc.
- **Brand Tone**: Playful, serious, luxurious, utilitarian, editorial, technical
- **Existing Stack**: Framework (React, Vue, SwiftUI, Jetpack Compose, Flutter, etc.)
- **Constraints**: Accessibility requirements (WCAG level), performance budget, dark/light mode

### 2. Design System Principles

#### Tokens First
Always define design tokens before components:
```css
:root {
  /* Color */
  --color-primary:      <hex>;
  --color-primary-soft: <hex>;
  --color-surface:      <hex>;
  --color-on-surface:   <hex>;
  --color-accent:       <hex>;
  --color-error:        <hex>;

  /* Typography */
  --font-display:  <font-stack>;
  --font-body:     <font-stack>;
  --font-mono:     <font-stack>;
  --text-xs:  0.75rem;
  --text-sm:  0.875rem;
  --text-md:  1rem;
  --text-lg:  1.25rem;
  --text-xl:  1.5rem;
  --text-2xl: 2rem;
  --text-3xl: 3rem;

  /* Spacing (4-point grid) */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-12: 3rem;
  --space-16: 4rem;

  /* Radius */
  --radius-sm:   4px;
  --radius-md:   8px;
  --radius-lg:   16px;
  --radius-full: 9999px;

  /* Shadow */
  --shadow-sm: 0 1px 3px rgba(0,0,0,.12);
  --shadow-md: 0 4px 16px rgba(0,0,0,.16);
  --shadow-lg: 0 8px 32px rgba(0,0,0,.20);

  /* Motion */
  --ease-out:   cubic-bezier(0.0, 0.0, 0.2, 1);
  --ease-in:    cubic-bezier(0.4, 0.0, 1.0, 1);
  --ease-spring:cubic-bezier(0.34, 1.56, 0.64, 1);
  --duration-fast:   150ms;
  --duration-normal: 250ms;
  --duration-slow:   400ms;
}
```

#### Typography Rules
- Never use more than 2 type families in one interface
- Display/heading font: expressive, memorable, characterful
- Body font: highly readable at small sizes, wide language support
- Line-height: 1.4–1.6 for body, 1.1–1.25 for headings
- Max line length: 60–75 characters for body text
- Avoid system fonts (Arial, Helvetica, system-ui) unless explicitly requested

#### Color Rules
- Minimum contrast ratio: 4.5:1 for normal text (WCAG AA), 3:1 for large text
- Use a dominant neutral palette + 1-2 accent colors maximum
- Dark mode: don't just invert — rethink surface hierarchy
- Avoid pure black (#000000) backgrounds; use deep tinted neutrals

#### Spacing & Layout
- Use a consistent 4pt or 8pt grid
- Establish clear visual hierarchy through size, weight, and spacing — not just color
- White space is not wasted space; it creates focus
- Align elements to a grid; avoid arbitrary pixel values

### 3. Platform-Specific Guidelines

#### Web
- Mobile-first responsive design by default
- Touch targets minimum 44×44px
- Keyboard navigability and focus-visible styles required
- Use `prefers-reduced-motion` media query for animations
- Semantic HTML (nav, main, section, article, aside)

#### iOS (SwiftUI)
- Follow Apple Human Interface Guidelines
- Use SF Symbols for iconography
- Respect safe area insets
- Prefer native components; customize via modifiers
- Support Dynamic Type for accessibility

#### Android (Jetpack Compose / Material 3)
- Follow Material Design 3 guidelines
- Use MaterialTheme tokens
- Support edge-to-edge display
- Implement proper back-stack navigation

#### Desktop
- Support keyboard shortcuts and menu bars
- Resize-aware layouts with min/max constraints
- Consider multi-window and multi-monitor scenarios

### 4. Component Patterns

When building components always provide:
1. **Default state**
2. **Hover / focus state**
3. **Active / pressed state**
4. **Disabled state**
5. **Loading / skeleton state** (where applicable)
6. **Error state** (for form elements)
7. **Empty state** (for data containers)

### 5. Motion Design
- Entrance animations: fade + translate (8–16px), 200–300ms, ease-out
- Exit animations: fade only, 150ms, ease-in
- State changes: cross-fade or morph, 150–250ms
- Looping animations (spinners, skeletons): subtle, 1–2s cycles
- Never animate more than 2 properties simultaneously unless orchestrated
- Use `will-change` sparingly; only on actively animating elements

### 6. Accessibility Checklist
- [ ] All interactive elements have visible focus indicators
- [ ] Color is never the sole means of conveying information
- [ ] Images have descriptive alt text; decorative images have `alt=""`
- [ ] Forms have associated labels (not just placeholder text)
- [ ] Error messages are descriptive and linked to fields via `aria-describedby`
- [ ] Page has a logical heading hierarchy (h1 → h2 → h3)
- [ ] Sufficient color contrast (4.5:1 for text, 3:1 for UI components)
- [ ] Motion can be disabled via `prefers-reduced-motion`

## Output Format

For each UI/UX task, deliver:
1. **Rationale** (2-3 sentences): aesthetic direction, key decisions
2. **Implementation**: complete, production-ready code
3. **Tokens / variables** defined at the top
4. **States**: all interactive states accounted for
5. **Accessibility notes**: any ARIA attributes or semantic choices explained

## Anti-Patterns to Avoid
- Generic "bootstrap-style" card grids with no visual identity
- Purple-gradient-on-white color schemes
- Overuse of rounded corners everywhere (choose a radius and be consistent)
- Shadows on every element (use sparingly for elevation hierarchy)
- Animations on every interaction (save motion for meaningful moments)
- Lorem ipsum as placeholder — use realistic content
- Fixed pixel widths that break at non-standard viewport sizes
