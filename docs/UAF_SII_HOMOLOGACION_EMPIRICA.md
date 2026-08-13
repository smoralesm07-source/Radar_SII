# Homologación empírica UAF–SII

## Objetivo

Perfeccionar el crosswalk UAF–SII utilizando evidencia observada por RUT: partir de los sujetos obligados efectivamente inscritos en la UAF, identificar todas sus actividades económicas vigentes publicadas por el SII y separar la actividad potencialmente vinculante de actividades accesorias, amplias o incidentales.

El propósito operacional es soportar consultas del tipo: **qué RUT presentan señales compatibles con una categoría de sujeto obligado y no aparecen en el registro UAF**, sin confundir una señal tributaria con una conclusión jurídica de incumplimiento.

## Fuentes

- UAF: Registro de Entidades Reportantes / sujetos obligados inscritos.
- SII: `PUB_NOM_ACTECOS.zip`, nómina de actividades económicas vigentes de contribuyentes personas jurídicas.
- `config/uaf_sii_crosswalk.csv`: crosswalk normativo/analítico anterior, utilizado como prior y no como verdad empírica.

## Productos

- `config/uaf_sii_crosswalk_v2.csv`: evidencia empírica sector UAF ↔ ACTECO SII.
- `config/uaf_sii_screening_policy.csv`: política final para decidir qué relaciones pueden utilizarse en screening de potenciales sujetos obligados.
- `docs/data/uaf_sii_empirical_sector_coverage.csv`: cobertura del cruce UAF contra la nómina SII de personas jurídicas por sector.
- `docs/data/uaf_sii_empirical_summary.json`: metadatos, conteos y fechas de fuente.

## Variables principales

Por cada combinación sector UAF–ACTECO se calculan:

- RUT UAF totales del sector.
- RUT UAF emparejados con SII personas jurídicas.
- soporte: RUT del sector que registran el ACTECO.
- cobertura dentro del sector.
- límite inferior de Wilson para controlar muestras pequeñas.
- pureza del código dentro de los inscritos UAF.
- lift frente a la frecuencia del código en el conjunto UAF.
- RUT SII totales con el código.
- RUT UAF con el código.
- universo bruto SII con el código que no figura en UAF.
- riesgo de falso positivo.
- respaldo del crosswalk normativo anterior.

## Política de screening

### A — ACTECO prioritario respaldado

Código con equivalencia normativa fuerte y respaldo empírico suficiente. Puede generar candidatos de screening. La condición de sujeto obligado debe confirmarse con la fuente sectorial correspondiente cuando exista registro o autorización específica.

### B — ACTECO candidato / firma empírica

Código parcial o asociación empírica relevante. Puede aumentar el score de un candidato o generar una cola secundaria de revisión, pero no sustenta por sí solo la calidad jurídica de sujeto obligado.

### C/D — Contexto, amplitud o muestra insuficiente

No generar candidatos únicamente por estos códigos. Se conservan para explicabilidad, auditoría, enriquecimiento y modelamiento.

### A_REGISTRO — Registro externo requerido

La obligación depende de una calidad jurídica, autorización, fiscalización o registro que no puede deducirse de ACTECO. El universo debe construirse desde la fuente sectorial y luego contrastarse con UAF.

### No evaluable con nómina SII PJ

Sectores donde la lista UAF presenta cobertura nula o muy baja en la nómina pública SII de personas jurídicas. No inferir candidatos desde ACTECO; recurrir al registro sectorial.

## Regla para la futura consulta de potenciales no inscritos

1. Tomar el universo SII vigente y excluir todos los RUT presentes en UAF.
2. Aplicar primero relaciones de prioridad A y luego B.
3. Deduplicar por RUT y conservar todas las señales explicativas.
4. Incorporar como variables de ranking cobertura, lift, amplitud del ACTECO y riesgo de falso positivo.
5. En sectores regulados, contrastar contra CMF, Banco Central, Aduanas, DGMN, SUSESO, Poder Judicial, Superintendencia de Casinos u otro registro sectorial aplicable.
6. Para `A_REGISTRO`, construir el universo desde el registro externo y no desde ACTECO.
7. Emitir el resultado como `POTENCIAL_SO_PARA_REVISION`, nunca como `SO_NO_INSCRITO_CONFIRMADO` solo por el cruce.
8. Mostrar evidencia trazable: sector UAF hipotético, ACTECO, glosa, métricas empíricas, fuente sectorial requerida y motivo del score.

## Interpretación

La presencia de un ACTECO SII es una señal OSINT de screening. No demuestra por sí misma que un contribuyente reúna todos los elementos jurídicos o materiales que activan la obligación de inscripción ante la UAF. La política prioriza sensibilidad para descubrir brechas, pero incorpora controles explícitos de especificidad para reducir falsos positivos y evitar conclusiones reputacionales no sustentadas.
