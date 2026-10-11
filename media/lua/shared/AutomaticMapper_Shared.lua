--[[
    AutomaticMapper_Shared.lua
    Configuraciones, constantes y utilidades compartidas para AutomaticMapper
--]]

AutomaticMapper = AutomaticMapper or {}
AutomaticMapper.Version = "1.0.0"

-- Presets de coordenadas aproximadas para las localidades principales de Knox (Build 42)
AutomaticMapper.TownPresets = {
    ["Muldraugh"]     = { minX = 10400, minY = 9200,  maxX = 11200, maxY = 10800 },
    ["West Point"]    = { minX = 11500, minY = 6400,  maxX = 12400, maxY = 7400  },
    ["Rosewood"]      = { minX = 7800,  minY = 11200, maxX = 8600,  maxY = 12000 },
    ["Riverside"]     = { minX = 5800,  minY = 5100,  maxX = 7000,  maxY = 5800  },
    ["March Ridge"]   = { minX = 9700,  minY = 12400, maxX = 10500, maxY = 13200 },
    ["Fallas Lake"]   = { minX = 6800,  minY = 8700,  maxX = 7600,  maxY = 9500  },
    ["Brandenburg"]   = { minX = 3800,  minY = 5800,  maxX = 4800,  maxY = 6800  },
    ["Echo Creek"]    = { minX = 3400,  minY = 10400, maxX = 4400,  maxY = 11400 },
    ["Louisville"]    = { minX = 11800, minY = 1000,  maxX = 14500, maxY = 4200  },
    ["Todo Knox"]     = { minX = 0,     minY = 0,     maxX = 30000, maxY = 30000 }
}

-- Función para verificar si un punto o caja se cruza con los límites seleccionados
function AutomaticMapper.isInBounds(x, y, x2, y2, bounds)
    if not bounds then return true end
    if x2 < bounds.minX or x > bounds.maxX then return false end
    if y2 < bounds.minY or y > bounds.maxY then return false end
    return true
end

-- Generador de ID determinista para edificios
function AutomaticMapper.getBuildingId(bld)
    local cx = math.floor((bld:getX() + bld:getX2()) / 2)
    local cy = math.floor((bld:getY() + bld:getY2()) / 2)
    local prefix = bld:isResidential() and "res" or (bld:isShop() and "com" or "gen")
    return string.format("bld_%s_%d_%d", prefix, cx, cy)
end

-- Limpieza de texto para claves y nombres
function AutomaticMapper.sanitizeName(str)
    if not str then return "unnamed" end
    local clean = string.gsub(string.lower(str), "[^%w_]", "_")
    return clean
end
