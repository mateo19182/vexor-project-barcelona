# CatastroAPI.es — Guía de integración

> Wrapper REST/JSON sobre los servicios SOAP/XML oficiales del Catastro español.
> Base URL: `https://api.catastro-api.es`

## Autenticación

```
Header: x-api-key: <API_KEY>
Accept: application/json
```

Plan Básico: €9/mes, 1.000 req/mes, 30 req/min.

---

## Flujo principal: Dirección → Datos del inmueble

### Paso 1 — Buscar la calle exacta

El nombre y tipo de vía deben coincidir exactamente con Catastro. Primero resolvemos.

```
GET /api/callejero/vias
  ?provincia=Madrid
  &municipio=Madrid
  &nombreVia=GRAN
```

**Respuesta:**

```json
{
  "numeroVias": 29,
  "vias": [
    {
      "codigoProvinciaIne": "28",
      "codigoVia": "8",
      "nombreVia": "GRAN VÍA",
      "tipoVia": "CL"
    }
  ],
  "errores": []
}
```

**Tipos de vía comunes:** CL (Calle), AV (Avenida), PS (Paseo/Passeig), PZ (Plaza), RU (Rúa), CM (Camino), CR (Carretera), TR (Travesía).

### Paso 2 — Obtener datos del inmueble

```
GET /api/callejero/inmueble-localizacion
  ?provincia=Madrid
  &municipio=Madrid
  &tipoVia=CL
  &nombreVia=GRAN VÍA
  &numero=1
  &planta=01        (opcional)
  &puerta=IZ        (opcional)
  &bloque=A         (opcional)
  &escalera=1       (opcional)
```

**Respuesta completa:**

```json
{
  "numeroInmuebles": 18,
  "inmuebles": [
    {
      "tipoBien": "UR",
      "referenciaCatastral": {
        "referenciaCatastral": "0847106VK4704F0006FI",
        "pc1": "0847106",
        "pc2": "VK4704F",
        "car": "0006",
        "cc1": "F",
        "cc2": "I"
      },
      "direccion": {
        "codigoProvinciaIne": "28",
        "nombreProvincia": "MADRID",
        "nombreMunicipio": "MADRID",
        "codigoPostal": "28013",
        "tipoVia": "CL",
        "nombreVia": "GRAN VÍA",
        "numero": "1",
        "bloque": "",
        "escalera": "",
        "planta": "01",
        "puerta": "IZ",
        "direccionCompleta": "CL GRAN VIA 1 Pl:01 Pt:IZ 28013 MADRID (MADRID)"
      },
      "datosEconomicos": {
        "uso": "Comercial",
        "superficieConstruida": "445",
        "coeficienteParticipacion": "6,350000",
        "añoConstruccion": "1907"
      },
      "unidadesConstructivas": [
        {
          "uso": "OCIO HOSTEL.",
          "bloque": "A",
          "escalera": "1",
          "planta": "01",
          "puerta": "IZ",
          "superficieTotal": "375",
          "tipologiaConstructiva": "HOSTELERIA-RESTAURACION"
        }
      ],
      "subparcelas": [
        {
          "codigoSubparcela": "001",
          "calificacionCatastral": "R",
          "claseCultivo": "OLIVAR",
          "intensidadProductiva": "0.8",
          "superficieSubparcela": "2500"
        }
      ],
      "localizacionRustica": {
        "codigoMunicipioAgregado": "123",
        "codigoZonaConcentracion": "456",
        "codigoPoligono": "001",
        "codigoParcela": "002",
        "nombreParaje": "EL CERRAL",
        "codigoParaje": "789"
      }
    }
  ],
  "errores": []
}
```

### Alternativa — Buscar por referencia catastral

Si ya tienes la RC (14-20 caracteres):

```
GET /api/callejero/inmueble-rc?rc=9872023VH5797S0001WX
```

Devuelve la misma estructura que `inmueble-localizacion`.

---

## Todos los campos que devuelve Catastro

### Datos de alto valor para nosotros


| Campo                          | Ruta JSON                                                   | Para qué lo usamos                                                |
| ------------------------------ | ----------------------------------------------------------- | ----------------------------------------------------------------- |
| **Superficie construida (m2)** | `inmuebles[].datosEconomicos.superficieConstruida`          | Multiplicar por €/m2 de zona → estimación de valor                |
| **Uso**                        | `inmuebles[].datosEconomicos.uso`                           | Clasificar: Residencial, Comercial, Oficinas, Industrial, Almacén |
| **Año de construcción**        | `inmuebles[].datosEconomicos.añoConstruccion`               | Antigüedad → ajuste en estimación (edificio nuevo vs 1900)        |
| **Código postal**              | `inmuebles[].direccion.codigoPostal`                        | Cruzar con datos MITMA de precio medio por CP                     |
| **Referencia catastral**       | `inmuebles[].referenciaCatastral.referenciaCatastral`       | ID único para cruzar con Registro, INSPIRE, sede electrónica      |
| **Coeficiente participación**  | `inmuebles[].datosEconomicos.coeficienteParticipacion`      | % del edificio que corresponde a esta unidad                      |
| **Tipología constructiva**     | `inmuebles[].unidadesConstructivas[].tipologiaConstructiva` | Detalle de uso real (HOSTELERIA, VIVIENDA COLECTIVA, etc.)        |
| **Superficie por unidad**      | `inmuebles[].unidadesConstructivas[].superficieTotal`       | Desglose m2 por planta/uso cuando hay varias unidades             |


### Datos complementarios


| Campo                          | Ruta JSON                                               | Nota                                                    |
| ------------------------------ | ------------------------------------------------------- | ------------------------------------------------------- |
| Dirección completa normalizada | `inmuebles[].direccion.direccionCompleta`               | Formato oficial Catastro                                |
| Tipo de bien (UR/RU)           | `inmuebles[].tipoBien`                                  | Urbano vs Rústico                                       |
| Provincia/Municipio            | `inmuebles[].direccion.nombreProvincia/nombreMunicipio` |                                                         |
| Subparcelas (rústica)          | `inmuebles[].subparcelas[]`                             | Solo fincas rústicas: cultivo, superficie, calificación |
| Localización rústica           | `inmuebles[].localizacionRustica`                       | Polígono, parcela, paraje                               |


### Lo que Catastro NO da

- **Valor catastral**: dato protegido, requiere certificado digital FNMT/Cl@ve.
- **Precio de mercado**: no existe en Catastro.
- **Precio de alquiler**: no existe en Catastro.
- **Titular/propietario**: dato protegido.

---

## Todos los endpoints disponibles


| Endpoint                               | Método | Descripción                                             |
| -------------------------------------- | ------ | ------------------------------------------------------- |
| `/api/callejero/provincias`            | GET    | Lista de provincias españolas                           |
| `/api/callejero/municipios`            | GET    | Municipios de una provincia                             |
| `/api/callejero/vias`                  | GET    | Calles de un municipio (buscar nombre exacto + tipoVia) |
| `/api/callejero/numeros`               | GET    | Números de portal de una calle                          |
| `/api/callejero/inmueble-localizacion` | GET    | **Inmuebles por dirección** (endpoint principal)        |
| `/api/callejero/inmueble-rc`           | GET    | Inmuebles por referencia catastral                      |
| `/api/callejero-codigos/provincias`    | GET    | Provincias por código INE                               |
| `/api/callejero-codigos/municipios`    | GET    | Municipios por código INE/MEH                           |
| `/api/callejero-codigos/vias`          | GET    | Calles por código de vía                                |


---

## Cómo estimar valor del inmueble (Catastro NO lo da directamente)

Catastro proporciona los **m2** y el **uso**. El precio hay que calcularlo cruzando con fuentes externas:

### Fórmula base

```
valor_estimado = superficie_m2 (Catastro) × precio_medio_eur_m2 (MITMA/otra fuente)
```

### Fuentes de precio €/m2


| Fuente                             | Dato                                  | Granularidad         | Coste                         |
| ---------------------------------- | ------------------------------------- | -------------------- | ----------------------------- |
| **MITMA (Ministerio Transportes)** | Precio medio venta + alquiler €/m2    | Por municipio y CP   | Gratis (CSV abiertos)         |
| **INE (IPV)**                      | Índice de precios vivienda trimestral | Por CCAA             | Gratis (API JSON)             |
| **Eurostat HPI**                   | House Price Index (ya integrado)      | Por país             | Gratis                        |
| **Barcelona Open Data**            | €/m2 oferta por barrio (ya integrado) | Por barrio BCN       | Gratis                        |
| **Idealista API**                  | Listings reales venta/alquiler        | Por dirección exacta | Pago / pedir acceso hackathon |
| **Registradores de España**        | Transacciones reales                  | Por zona             | Informes públicos             |


### Ajustes sobre la estimación base


| Factor                    | Dato Catastro              | Ajuste                                                                     |
| ------------------------- | -------------------------- | -------------------------------------------------------------------------- |
| Antigüedad                | `añoConstruccion`          | Edificio pre-1960 → descuento ~10-20% vs media zona                        |
| Uso                       | `uso`                      | Comercial/Oficinas tiene distinto €/m2 que Residencial                     |
| Planta                    | `planta`                   | Pisos altos → premium ~5-10% (no viene de Catastro, pero se puede inferir) |
| Coeficiente participación | `coeficienteParticipacion` | Proporción del edificio → valida que los m2 son coherentes                 |


### Para alquiler

```
alquiler_mensual_estimado = superficie_m2 × precio_alquiler_eur_m2_mes (MITMA por municipio)
```

MITMA publica trimestralmente el precio medio del alquiler por municipio y CP. Es la fuente más fiable y gratuita.

---

## Errores comunes y cómo evitarlos


| Error                                           | Causa                                      | Solución                                                  |
| ----------------------------------------------- | ------------------------------------------ | --------------------------------------------------------- |
| `400: El tipo de vía debe ser válido`           | tipoVia incorrecto (ej: `CL` para un `PS`) | Usar `/vias` primero para obtener tipoVia correcto        |
| `0 inmuebles` con datos aparentemente correctos | Nombre de calle no coincide exactamente    | Usar `/vias` con búsqueda parcial (≥3 chars)              |
| Muchos inmuebles (50-200+)                      | Edificio grande sin filtrar planta/puerta  | Añadir `planta` y `puerta` para filtrar unidad específica |
| `401 Unauthorized`                              | API key inválida o ausente                 | Verificar header `x-api-key`                              |
| `429 Too Many Requests`                         | Excedido rate limit (30 req/min en básico) | Implementar backoff o upgrade plan                        |


---

## Flujo recomendado para el agente

```
Dirección del deudor (texto libre)
    │
    ▼
[1] Geocoding (Nominatim/Photon) → provincia, municipio, calle, número
    │
    ▼
[2] GET /api/callejero/vias → nombre exacto + tipoVia
    │
    ▼
[3] GET /api/callejero/inmueble-localizacion → m2, uso, año, RC, CP
    │
    ▼
[4] MITMA open data → precio_medio_eur_m2 por CP/municipio
    │
    ▼
[5] Estimación = m2 × precio_medio_eur_m2
    │
    ├── valor_venta_estimado (banda min-max)
    └── alquiler_mensual_estimado (banda min-max)
```

Cada dato lleva su fuente trazable. Si algún paso falla, se documenta el gap explícitamente.