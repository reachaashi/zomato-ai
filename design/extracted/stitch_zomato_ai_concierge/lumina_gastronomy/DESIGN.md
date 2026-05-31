---
name: Lumina Gastronomy
colors:
  surface: '#1e0f10'
  surface-dim: '#1e0f10'
  surface-bright: '#473435'
  surface-container-lowest: '#180a0b'
  surface-container-low: '#271718'
  surface-container: '#2b1b1c'
  surface-container-high: '#372626'
  surface-container-highest: '#423031'
  on-surface: '#f9dcdc'
  on-surface-variant: '#e3bdbf'
  inverse-surface: '#f9dcdc'
  inverse-on-surface: '#3e2c2d'
  outline: '#aa888a'
  outline-variant: '#5b4041'
  surface-tint: '#ffb2b7'
  primary: '#ffb2b7'
  on-primary: '#67001b'
  primary-container: '#ff516a'
  on-primary-container: '#5b0017'
  inverse-primary: '#bc0b3b'
  secondary: '#a4c9ff'
  on-secondary: '#00315d'
  secondary-container: '#0267b8'
  on-secondary-container: '#d6e5ff'
  tertiary: '#eec200'
  on-tertiary: '#3c2f00'
  tertiary-container: '#cea700'
  on-tertiary-container: '#4e3e00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffdadb'
  primary-fixed-dim: '#ffb2b7'
  on-primary-fixed: '#40000d'
  on-primary-fixed-variant: '#92002a'
  secondary-fixed: '#d4e3ff'
  secondary-fixed-dim: '#a4c9ff'
  on-secondary-fixed: '#001c39'
  on-secondary-fixed-variant: '#004883'
  tertiary-fixed: '#ffe083'
  tertiary-fixed-dim: '#eec200'
  on-tertiary-fixed: '#231b00'
  on-tertiary-fixed-variant: '#574500'
  background: '#1e0f10'
  on-background: '#f9dcdc'
  surface-variant: '#423031'
typography:
  display-lg:
    fontFamily: Outfit
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Outfit
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Outfit
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Outfit
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Outfit
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Outfit
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Outfit
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Outfit
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  container-padding: 24px
  gutter: 16px
  stack-sm: 12px
  stack-md: 24px
  stack-lg: 48px
---

## Brand & Style
This design system centers on a premium, high-tech culinary experience. It targets discerning food enthusiasts who value AI-driven precision and a sophisticated aesthetic. The emotional response is one of exclusivity, intelligence, and appetite-stimulating modernism.

The design style is **Glassmorphism**, leveraging deep, layered backgrounds with frosted-glass surfaces. It utilizes translucent layers and vibrant radial glows to simulate depth within a dark, infinite space. The UI feels ethereal yet structured, prioritizing high-contrast content against a moody, cinematic backdrop.

## Colors
The palette is rooted in a **Deep Slate and Navy** foundation to provide a luxurious, low-light environment. **Vibrant Rose** serves as the primary action color, evoking passion and appetite. **Amber** is strictly reserved for ratings and excellence markers, while **Indigo** denotes financial tiers and budget-related data. 

Interactive elements utilize a Rose-to-Crimson gradient to create a sense of glowing energy. Surface colors rely on varying opacities of white or the secondary slate to create the signature glass effect without sacrificing legibility.

## Typography
**Outfit** is the sole typeface, chosen for its geometric clarity and modern, open terminals. Headlines use a tighter letter-spacing and heavier weights to command attention against the dark background. Body text is kept clean and sufficiently spaced to ensure maximum readability through frosted glass overlays. Captions and labels often utilize uppercase styling and increased tracking to provide a technical, "AI-metadata" feel.

## Layout & Spacing
The layout follows a **Fluid Grid** model with a maximum content width of 1440px on desktop. On mobile, a standard 4-column grid is used with 24px side margins.

Spacing is built on an 8px rhythmic scale. Cards and sections utilize generous internal padding (24px+) to allow the glassmorphic background blurs to breathe. Content clusters should be grouped using the `stack-sm` or `stack-md` units to maintain a clear hierarchy between restaurant details and metadata labels.

## Elevation & Depth
Depth is achieved through a combination of **Backdrop Blurs** and **Radial Glows**. 
- **Tier 1 (Base):** Deep Slate solid color (#0F172A).
- **Tier 2 (Cards/Sheets):** `rgba(30, 41, 59, 0.7)` with a `backdrop-filter: blur(12px)` and a 1px solid border of `rgba(255, 255, 255, 0.08)`.
- **Tier 3 (Floating Elements/Modals):** Same as Tier 2 but with a subtle outer glow using the primary Rose color at 10% opacity.
- **Visual Interest:** Large, soft radial gradients in Rose or Indigo should be placed behind key cards to create a "bloom" effect that shines through the glass layers.

## Shapes
A **Rounded** strategy is applied to soften the technical nature of the AI. Standard components like cards and buttons use a 0.5rem (8px) radius. Larger containers, such as bottom sheets and main dashboard cards, use `rounded-xl` (1.5rem/24px) to create a friendly, modern containerized look. Interactive pills and badges use a full circular radius (pill-shaped).

## Components
- **Buttons:** Primary buttons use the Rose-to-Crimson gradient with white text. Secondary buttons are "ghost" style with a 1px white border at 0.15 opacity and high-blur backdrop.
- **Cards:** Restaurant cards feature a ranked badge in the top-left (using the Amber rating color). The footer of the card should be a semi-transparent dark strip to house the "Match Score" AI indicator.
- **Ranked Badges:** Small, circular or pill-shaped elements using a high-contrast Amber background with black text for the "AI Match %".
- **Segmented Controls:** A dark, recessed track with a glass-morphic "sliding" thumb that highlights the active selection.
- **Sliders:** For budget selection, the track is Deep Navy, while the active range and handle are Indigo with a subtle outer glow.
- **Input Fields:** Minimalist designs with only a bottom border or a very faint glass background; focus states trigger a Rose-colored outer glow and border transition.
- **Chips:** Used for cuisine types; these are translucent grey with a 1px border, turning Rose on selection.