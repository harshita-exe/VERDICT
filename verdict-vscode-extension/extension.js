const vscode = require('vscode');
const http = require('http');

let diagnosticCollection;
let outputChannel;

function activate(context) {
  diagnosticCollection = vscode.languages.createDiagnosticCollection('verdict');
  outputChannel = vscode.window.createOutputChannel('Verdict');
  context.subscriptions.push(diagnosticCollection, outputChannel);

  const disposable = vscode.commands.registerCommand('verdict.reviewCurrentFile', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showErrorMessage('Verdict: Open a file to review first.');
      return;
    }

    const code = editor.document.getText();
    if (!code.trim()) {
      vscode.window.showErrorMessage('Verdict: The current file is empty.');
      return;
    }

    vscode.window.setStatusBarMessage('$(sync~spin) Verdict: reviewing your code...', 4000);

    try {
      const result = await callVerdictServer(code);
      showResults(editor, result);
    } catch (err) {
      vscode.window.showErrorMessage(
        'Verdict: Could not reach the review server. Make sure it is running (python app.py) ' +
        'at http://127.0.0.1:5000, then try again. (' + err.message + ')'
      );
    }
  });

  context.subscriptions.push(disposable);
}

function callVerdictServer(code) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify({ code });
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: 5000,
        path: '/api/review',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(payload),
        },
        timeout: 30000,
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            if (parsed.error) reject(new Error(parsed.error));
            else resolve(parsed);
          } catch (e) {
            reject(new Error('Server returned an unexpected response.'));
          }
        });
      }
    );
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timed out.'));
    });
    req.write(payload);
    req.end();
  });
}

const SEVERITY_MAP = {
  critical: vscode.DiagnosticSeverity.Error,
  high: vscode.DiagnosticSeverity.Error,
  medium: vscode.DiagnosticSeverity.Warning,
  low: vscode.DiagnosticSeverity.Information,
};

function showResults(editor, result) {
  const doc = editor.document;
  const diagnostics = [];

  for (const issue of result.issues_by_severity || []) {
    let line = 0;
    const match = /Line (\d+)/.exec(issue.detail || '');
    if (match) {
      line = Math.max(0, parseInt(match[1], 10) - 1);
    }
    line = Math.min(line, Math.max(0, doc.lineCount - 1));
    const range = doc.lineAt(line).range;

    const diag = new vscode.Diagnostic(
      range,
      `[Verdict/${issue.source}] (${(issue.severity || 'low').toUpperCase()}) ${issue.detail}`,
      SEVERITY_MAP[issue.severity] || vscode.DiagnosticSeverity.Information
    );
    diag.source = 'Verdict';
    diagnostics.push(diag);
  }
  diagnosticCollection.set(doc.uri, diagnostics);

  outputChannel.clear();
  outputChannel.appendLine('='.repeat(50));
  outputChannel.appendLine('VERDICT CODE REVIEW');
  outputChannel.appendLine('='.repeat(50));
  outputChannel.appendLine(`Recommendation: ${result.recommendation}`);
  outputChannel.appendLine(`  (${result.recommendation_detail || ''})`);
  outputChannel.appendLine(`Overall Quality: ${result.overall_quality}`);
  outputChannel.appendLine(`Total Issues: ${result.total_issues}`);
  outputChannel.appendLine('');
  outputChannel.appendLine(`Summary: ${result.summary}`);

  if (result.guidelines_used && result.guidelines_used.length) {
    outputChannel.appendLine('');
    outputChannel.appendLine('Guidelines checked (RAG):');
    result.guidelines_used.forEach((g) => outputChannel.appendLine(`  - ${g}`));
  }
  if (result.was_revised) {
    outputChannel.appendLine('');
    outputChannel.appendLine(`[Self-reflection revised the summary: ${result.reflection_note}]`);
  }

  outputChannel.appendLine('');
  outputChannel.appendLine('-'.repeat(50));
  (result.issues_by_severity || []).forEach((issue, i) => {
    outputChannel.appendLine(`${i + 1}. [${(issue.severity || '').toUpperCase()}] (${issue.type}) via ${issue.source}`);
    outputChannel.appendLine(`   ${issue.detail}`);
    outputChannel.appendLine('');
  });

  outputChannel.show(true);
  vscode.window.showInformationMessage(
    `Verdict: ${result.recommendation} — ${result.total_issues} issue(s) found. See Output panel and inline squiggles.`
  );
}

function deactivate() {
  if (diagnosticCollection) diagnosticCollection.dispose();
}

module.exports = { activate, deactivate };
