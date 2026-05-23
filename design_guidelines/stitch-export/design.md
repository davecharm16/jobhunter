---
name: Job Hunter
source: Stitch project 14722049854544467629 ("Drift-Checked Job Hunter")
exported: 2026-05-23
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#464555'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#777587'
  outline-variant: '#c7c4d8'
  surface-tint: '#4d44e3'
  primary: '#3525cd'
  on-primary: '#ffffff'
  primary-container: '#4f46e5'
  on-primary-container: '#dad7ff'
  inverse-primary: '#c3c0ff'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#7e3000'
  on-tertiary: '#ffffff'
  tertiary-container: '#a44100'
  on-tertiary-container: '#ffd2be'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0f0069'
  on-primary-fixed-variant: '#3323cc'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#ffdbcc'
  tertiary-fixed-dim: '#ffb695'
  on-tertiary-fixed: '#351000'
  on-tertiary-fixed-variant: '#7b2f00'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  display:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  container-max: 1440px
  sidebar-width: 260px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 40px
  stack-xs: 4px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 24px
---

## Brand & Style
The design system is built on a foundation of **"Anti-Slop" Modernism**. It prioritizes extreme clarity, utility, and a high-performance aesthetic for job seekers who value precision. The brand personality is professional, empowering, and reliable, functioning as a high-tier executive assistant.

The visual style is **Corporate / Modern**, characterized by a clean white canvas, generous whitespace, and a rigid information hierarchy. It uses subtle depth and thin borders to organize content without visual clutter, ensuring that the user's career documents remain the primary focus.

## Colors
The palette is rooted in a professional "Deep Navy" and "Vibrant Blue" combination.
- **Primary Blue:** Used for high-priority actions, links, and progress indicators. It signals movement and advancement.
- **Deep Navy:** Used for primary headings and body text to ensure maximum readability and a sense of authority.
- **Subtle Grays:** A range of Slate and Gray tones are used for borders, secondary descriptions, and inactive states to create a soft UI structure.
- **Background:** A pure white (`#FFFFFF`) background is used for the main workspace, with a very light neutral gray (`#F8FAFC`) used for sidebar or container backgrounds to provide subtle separation.

## Typography
This design system utilizes **Inter** exclusively to maintain a functional, systematic, and utilitarian feel.
- **Scale:** High contrast between headlines and body text is used to guide the eye.
- **Weights:** Semi-bold (600) is preferred for headers to provide structure, while Regular (400) is used for all long-form body text.
- **Labels:** Small, medium-weight labels are used for sidebar categories and metadata (e.g., "LAST UPDATED").

## Layout & Spacing
The layout uses a **Fixed Sidebar + Fluid Content** model.
- **Sidebar:** Fixed at 260px, containing navigation and the "Profile Completion" widget.
- **Grid:** A 12-column grid is used for the main content area. Document cards typically span 3 or 4 columns depending on screen width.
- **Rhythm:** A strict 8px base unit drives all spacing. Elements are grouped using 16px or 24px gaps to create clear visual clusters.
- **Breakpoints:**
  - *Mobile (<768px):* Sidebar transforms into a bottom bar or hidden drawer; margins reduce to 16px.
  - *Tablet (768px - 1024px):* Sidebar collapses to icons only; 2-column card layout.
  - *Desktop (>1024px):* Full sidebar; 3 or 4-column card layout.

## Elevation & Depth
Depth is handled through **Low-Contrast Outlines** and **Tonal Layering** rather than heavy shadows.
- **Surface 0 (Background):** White (#FFFFFF).
- **Surface 1 (Cards/Sidebar):** Neutral Gray (#F8FAFC) or White with a 1px border (#E2E8F0).
- **Shadows:** Use a single, highly diffused "Ambient Shadow" for active states only: `0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)`.
- **Active States:** Subtle inner glows or 2px primary-colored borders denote selection.

## Shapes
The shape language is **Soft (0.25rem base)**, reinforcing a professional and tailored feel without appearing too "bubbly" or "playful."
- **Small Elements (Inputs, Buttons):** 4px (0.25rem).
- **Medium Elements (Cards, Banners):** 8px (0.5rem).
- **Large Elements (Modals, Feature Sections):** 12px (0.75rem).
- **Icons:** Enclosed in circles or soft squares with a 20% opacity background of their own color.

## Components
- **Primary Buttons:** Solid Vibrant Blue with white text. High-contrast, 44px height for touch targets.
- **Document Cards:** White background, 1px Slate-200 border. Features a thumbnail preview of the resume, document title in Navy, and secondary metadata in Gray.
- **Sidebar Nav:** High-legibility icons paired with Body-MD text. The active state uses a 3px vertical primary-blue bar on the left edge.
- **Input Fields:** 1px border (#E2E8F0), 12px horizontal padding. Focus state switches border to Primary Blue with a subtle 2px outer glow.
- **Profile Widget:** A specialized container in the sidebar featuring a circular progress ring and a "Complete Now" call to action.
- **Chips:** Used for document tagging (e.g., "Professional", "Resume"). Light gray background with navy text, 2px roundedness.
