-- Redline window appearance. Personal Hyprland overrides take precedence.
-- Hex literals are recolored with the selected palette during staging.
local function rgb(hex) return "rgb(" .. hex:sub(2) .. ")" end
local accent = rgb("#d51b36")
local inactive = rgb("#391018")
hl.config({
  general = {
    gaps_in = 5,
    gaps_out = 10,
    border_size = 1,
    col = { active_border = accent, inactive_border = inactive },
  },
  group = { col = { border_active = accent, border_inactive = inactive } },
  decoration = {
    rounding = 18,
    shadow = {
      enabled = true,
      range = 18,
      render_power = 3,
      color = "rgba(00000055)",
    },
  },
})
