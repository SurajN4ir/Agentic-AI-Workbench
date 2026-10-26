/* Browser-driven acceptance using real Chrome through the bundled Playwright Core. */
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_CORE)

const root = path.resolve(__dirname, '..', '..')
const runDir = __dirname
const fixture = path.join(root, 'eval', 'fixtures', 'corpus', 'turbine_operating_manual.txt')
const baseUrl = 'http://127.0.0.1:3000'
const attempt = process.env.BROWSER_ATTEMPT || 'browser-run'
const results = {
  timestamp: new Date().toISOString(),
  mode: 'browser_driven_chrome_playwright',
  base_url: baseUrl,
  fixture: 'eval/fixtures/corpus/turbine_operating_manual.txt',
  checks: [],
  browser_api_responses: [],
  screenshots: [],
  downloaded_files: [],
}

function record(id, passed, detail) {
  results.checks.push({ id, status: passed ? 'PASS' : 'FAIL', detail })
  console.log(`${passed ? 'PASS' : 'FAIL'} ${id}: ${detail}`)
}

async function capture(page, name) {
  const target = path.join(runDir, `${attempt}-${name}`)
  await page.screenshot({ path: target, fullPage: true })
  results.screenshots.push(path.basename(target))
}

async function main() {
  if (!process.env.AUDIT_ANALYST_PASSWORD || !process.env.AUDIT_ADMIN_PASSWORD) {
    throw new Error('Synthetic audit account environment variables are missing')
  }
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_EXE,
    args: ['--disable-background-networking', '--disable-component-update', '--no-first-run'],
  })
  try {
    const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1536, height: 1000 } })
    const page = await context.newPage()
    page.setDefaultTimeout(30000)
    page.on('response', (response) => {
      if (response.url().includes('/api/v1/')) {
        results.browser_api_responses.push({
          method: response.request().method(),
          path: new URL(response.url()).pathname,
          status: response.status(),
        })
      }
    })
    page.on('pageerror', (error) => results.page_errors?.push(String(error)))
    results.page_errors = []

    await page.goto(baseUrl, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: 'Sovereign Sign In' }).waitFor()
    await capture(page, 'browser-00-sign-in.png')
    record('browser_root_and_health', (await page.getByText('ok', { exact: true }).count()) >= 2,
      'Chrome loaded the UI from loopback; API and database health indicators rendered.')

    await page.locator('input[type="text"]').fill('audit_analyst')
    await page.locator('input[type="password"]').fill(process.env.AUDIT_ANALYST_PASSWORD)
    await page.getByRole('button', { name: 'Sign In', exact: true }).click()
    await page.getByText('audit_analyst', { exact: true }).waitFor({ timeout: 30000 })
    record('browser_login', true, 'Synthetic analyst authenticated through the browser login form.')
    await capture(page, 'browser-01-authenticated.png')

    await page.getByRole('button', { name: 'Knowledge Base (RAG)' }).click()
    await page.getByRole('heading', { name: /Knowledge Hub & Chunk Inspector/ }).waitFor()
    await page.getByRole('button', { name: 'Ingest Document' }).click()
    await page.locator('input[type="file"]').setInputFiles(fixture)
    const uploadWait = page.waitForResponse((response) =>
      response.url().includes('/api/v1/knowledge/upload') && response.request().method() === 'POST',
      { timeout: 180000 },
    )
    await page.getByRole('button', { name: 'Start Ingestion' }).click()
    const uploadResponse = await uploadWait
    await page.getByText('turbine_operating_manual.txt', { exact: false }).first().waitFor({ timeout: 30000 })
    record('browser_document_upload', uploadResponse.ok(),
      `Browser file input submitted the synthetic manual; HTTP ${uploadResponse.status()}.`)
    await capture(page, 'browser-02-uploaded.png')

    await page.getByRole('button', { name: 'Chunks', exact: true }).first().click()
    const chunkEvidence = await page.locator('body').innerText()
    const chunkInspected = /Chunk Inspector: turbine_operating_manual\.txt/i.test(chunkEvidence) && /5 total chunks/.test(chunkEvidence)
    record('browser_knowledge_hub_chunk_inspection', chunkInspected,
      chunkInspected ? 'Opened the uploaded document chunk inspector and saw chunk detail content.' : 'Chunk inspector did not expose expected detail content.')
    await capture(page, 'browser-03-chunk-inspector.png')
    const chunkDrawer = page.locator('div.fixed.inset-0').filter({ hasText: 'Chunk Inspector: turbine_operating_manual.txt' }).last()
    if (await chunkDrawer.count()) await chunkDrawer.locator('button').first().click()

    await page.getByRole('button', { name: /Hybrid Retrieval & Ranking Tester/ }).click()
    await page.getByRole('heading', { name: 'Hybrid Query Execution' }).waitFor()
    await page.getByPlaceholder(/maximum turbine bearing temperature limit/).fill(
      'What is the specified casing stud tightening torque for the TG-8500 turbine?',
    )
    const searchWait = page.waitForResponse((response) =>
      response.url().includes('/api/v1/knowledge/search') && response.request().method() === 'POST',
    )
    await page.getByRole('button', { name: 'Run Hybrid Search' }).click()
    const searchResponse = await searchWait
    await page.waitForFunction(() => document.body.innerText.includes('Specified Casing Stud Tightening Torque: 450 Nm'), null, { timeout: 30000 })
    const searchBody = await page.locator('body').innerText()
    record('browser_rag_query', searchResponse.ok() && searchBody.includes('450 Nm'),
      `Hybrid search completed from UI; HTTP ${searchResponse.status()}, retrieved the synthetic 450 Nm fact.`)
    await capture(page, 'browser-04-rag-search.png')

    await page.getByRole('button', { name: 'Agent Workbench' }).click()
    const prompt = page.locator('textarea').first()
    await prompt.fill('Search the uploaded turbine operating manual for the specified casing stud tightening torque. State the exact value and cite the source filename.')
    const streamWait = page.waitForResponse((response) =>
      response.url().includes('/api/v1/agent/stream') && response.request().method() === 'POST',
      { timeout: 30000 },
    )
    await page.getByRole('button', { name: 'Execute Workflow' }).click()
    const streamResponse = await streamWait
    await page.waitForFunction(() => document.body.innerText.includes('Task finished'), null, { timeout: 240000 })
    const responseBody = await page.locator('body').innerText()
    const grounded = await page.getByText('✓ Evidence Checks Passed', { exact: true }).count()
    const citedManual = responseBody.includes('turbine_operating_manual.txt')
    const citedTorque = responseBody.includes('450 Nm')
    record('browser_agent_rag_citation', streamResponse.ok() && grounded > 0 && citedManual && citedTorque,
      `Agent stream HTTP ${streamResponse.status()}; grounded badge=${grounded > 0}; source=${citedManual}; 450 Nm=${citedTorque}.`)
    await capture(page, 'browser-05-agent-citation.png')

    const citationButton = page.getByRole('button', { name: /turbine_operating_manual\.txt/ }).first()
    let citationInspectorOpened = false
    if (await citationButton.count()) {
      await citationButton.click()
      await page.getByRole('heading', { name: 'Citation & Grounding Inspector' }).waitFor({ timeout: 15000 })
      citationInspectorOpened = (await page.getByText('SOURCE CHECKS PASSED', { exact: true }).count()) > 0
    }
    record('browser_citation_inspector', citationInspectorOpened,
      citationInspectorOpened ? 'Clicked the cited source and opened its verified grounding inspector.' : 'No verified citation inspector opened.')

    let citationNavigation = false
    if (citationInspectorOpened) {
      await page.getByRole('button', { name: 'View in Knowledge Hub', exact: true }).click()
      await page.getByRole('heading', { name: /Knowledge Hub & Chunk Inspector/ }).waitFor({ timeout: 15000 })
      await page.waitForFunction(
        () => document.body.innerText.includes('Chunk UUID:') && !document.body.innerText.includes('Fetching chunk metadata...'),
        null,
        { timeout: 30000 },
      )
      const navigationBody = await page.locator('body').innerText()
      citationNavigation = navigationBody.includes('turbine_operating_manual.txt') && navigationBody.includes('Chunk UUID:')
      const detailClose = page.getByRole('button', { name: 'Close', exact: true }).last()
      if (await detailClose.count()) await detailClose.click()
      const destinationDrawer = page.locator('div.fixed.inset-0').filter({ hasText: 'Chunk Inspector: turbine_operating_manual.txt' }).last()
      if (await destinationDrawer.count()) {
        await destinationDrawer.locator('button').first().click()
        await destinationDrawer.waitFor({ state: 'detached', timeout: 10000 })
      }
    }
    record('browser_citation_navigation', citationNavigation,
      citationNavigation ? 'Citation navigation returned to the matching Knowledge Hub document.' : 'Citation-to-Knowledge-Hub navigation did not complete.')
    await capture(page, 'browser-06-citation-navigation.png')

    await page.getByRole('button', { name: 'Agent Workbench' }).click()
    const generationPrompts = [
      {
        id: 'docx_generation',
        filename: 'browser_demo_report.docx',
        prompt: 'Use doc_gen exactly once with this complete argument object and no extra fields: {"format":"docx","title":"Synthetic Turbine Torque Verification","filename":"browser_demo_report.docx","sections":[{"heading":"Torque","body":"The uploaded turbine operating manual specifies casing stud tightening torque of 450 Nm. Source: turbine_operating_manual.txt."}]}. Do not include a table. After the tool succeeds, stop and report the filename.',
      },
      {
        id: 'xlsx_generation',
        filename: 'browser_demo_metrics.xlsx',
        prompt: 'Use doc_gen exactly once with this complete argument object and no extra fields: {"format":"xlsx","title":"Synthetic Turbine Metrics","filename":"browser_demo_metrics.xlsx","table":{"headers":["Metric","Value","Source"],"rows":[["Casing stud tightening torque","450 Nm","turbine_operating_manual.txt"]]}}. Do not include sections. After the tool succeeds, stop and report the filename.' ,
      },
    ]
    for (const item of generationPrompts) {
      await page.locator('textarea').first().fill(item.prompt)
      const generateStream = page.waitForResponse((response) =>
        response.url().includes('/api/v1/agent/stream') && response.request().method() === 'POST',
        { timeout: 30000 },
      )
      await page.getByRole('button', { name: 'Execute Workflow' }).click()
      const generationResponse = await generateStream
      await page.waitForFunction(() => document.body.innerText.includes('Task finished'), null, { timeout: 240000 })
      const body = await page.locator('body').innerText()
      const generated = body.includes(item.filename)
      record(`browser_${item.id}`, generationResponse.ok() && generated,
        `Agent UI stream HTTP ${generationResponse.status()}; expected file listed=${generated}.`)
      await capture(page, `browser-${item.id}.png`)
      if (item.id === 'docx_generation' && generationResponse.ok() && !generated) {
        await page.locator('textarea').first().fill(item.prompt)
        const retryStream = page.waitForResponse((response) =>
          response.url().includes('/api/v1/agent/stream') && response.request().method() === 'POST',
          { timeout: 30000 },
        )
        await page.getByRole('button', { name: 'Execute Workflow' }).click()
        const retryResponse = await retryStream
        await page.waitForFunction(() => document.body.innerText.includes('Task finished'), null, { timeout: 240000 })
        const retryBody = await page.locator('body').innerText()
        const retryGenerated = retryBody.includes(item.filename)
        record('browser_docx_generation_retry', retryResponse.ok() && retryGenerated,
          `Second agent UI attempt HTTP ${retryResponse.status()}; expected file listed=${retryGenerated}.`)
        await capture(page, 'browser-docx_generation_retry.png')
      }
    }

    for (const filename of ['browser_demo_report.docx', 'browser_demo_metrics.xlsx']) {
      const link = page.getByRole('link', { name: 'Download' }).filter({ has: page.locator('svg') }).first()
      const fileRow = page.locator('div.flex.items-center.justify-between').filter({ hasText: filename }).filter({ has: page.getByRole('link', { name: 'Download' }) }).first()
      const targetLink = fileRow.getByRole('link', { name: 'Download' }).first()
      let downloaded = false
      if (await targetLink.count()) {
        const downloadWait = page.waitForEvent('download', { timeout: 30000 })
        await targetLink.click()
        const download = await downloadWait
        const target = path.join(runDir, 'downloads', filename)
        await fs.mkdir(path.dirname(target), { recursive: true })
        await download.saveAs(target)
        const stat = await fs.stat(target)
        downloaded = stat.size > 0 && download.suggestedFilename() === filename
        results.downloaded_files.push({ filename, size_bytes: stat.size, saved_to: path.relative(root, target).replaceAll('\\', '/') })
      }
      record(`browser_download_${path.extname(filename).slice(1)}`, downloaded,
        downloaded ? `Browser download completed for ${filename}.` : `Download link failed or output was empty for ${filename}.`)
    }

    await capture(page, 'browser-08-final-artifacts.png')
    record('browser_console_errors', results.page_errors.length === 0,
      results.page_errors.length ? results.page_errors.join(' | ') : 'No uncaught browser page errors.')
    await context.close()
  } finally {
    await browser.close()
  }

  results.summary = {
    passed: results.checks.filter((check) => check.status === 'PASS').length,
    failed: results.checks.filter((check) => check.status === 'FAIL').length,
    total: results.checks.length,
  }
  results.status = results.summary.failed === 0 ? 'PASS' : 'PARTIAL_OR_FAIL'
  await fs.writeFile(path.join(runDir, `browser_acceptance_${attempt}.json`), JSON.stringify(results, null, 2) + '\n')
  console.log(JSON.stringify(results.summary))
  if (results.summary.failed) process.exitCode = 1
}

main().catch(async (error) => {
  results.fatal_error = String(error && error.stack ? error.stack : error)
  results.summary = {
    passed: results.checks.filter((check) => check.status === 'PASS').length,
    failed: results.checks.filter((check) => check.status === 'FAIL').length + 1,
    total: results.checks.length + 1,
  }
  results.status = 'FAIL'
  await fs.writeFile(path.join(runDir, `browser_acceptance_${attempt}.json`), JSON.stringify(results, null, 2) + '\n')
  console.error(results.fatal_error)
  process.exitCode = 1
})
