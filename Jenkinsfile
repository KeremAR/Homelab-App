@Library('homelab-shared-library') _

def lintConfig = [
    pythonTargets: [
        'user-service',
        'todo-service'
    ],
    nodePackageDirs: [
        'frontend'
    ],
    dockerfiles: [
        'user-service/Dockerfile',
        'todo-service/Dockerfile',
        'frontend/Dockerfile'
    ]
]

def unitTestServices = [
    [
        name: 'user-service',
        target: 'user-service',
        requirementsFile: 'user-service/requirements-test.txt',
        testPath: '.',
        coverageThreshold: 70
    ],
    [
        name: 'todo-service',
        target: 'todo-service',
        requirementsFile: 'todo-service/requirements-test.txt',
        testPath: '.',
        coverageThreshold: 70
    ]
]

def securityConfig = [
    trivySkipDirs: [
        '**/node_modules',
        '**/.venv',
        '**/.venvs',
        '**/venv',
        '**/__pycache__',
        '.git',
        'coverage-reports'
    ]
]

def sonarConfig = [
    projectKey: 'homelab-app',
    sources: [
        'user-service',
        'todo-service',
        'frontend'
    ],
    coverageReports: [
        'coverage-reports/user-service/coverage.xml',
        'coverage-reports/todo-service/coverage.xml'
    ],
    fetchIssues: true,
    fetchIssuesConfig: [
        severities: ['BLOCKER', 'CRITICAL', 'MAJOR'],
        statuses: ['OPEN', 'CONFIRMED'],
        maxIssues: 100,
        maxIssuesToPrint: 100
    ],
    extraProperties: [
        'sonar.python.version': '3.11'
    ]
]

pipeline {
    agent {
        kubernetes {
            yaml ciLintPodTemplate()
            defaultContainer 'jnlp'
        }
    }

    options {
        skipDefaultCheckout(true)
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Linting') {
            parallel {
                stage('Python') {
                    steps {
                        runPythonLinting(
                            targets: lintConfig.pythonTargets,
                            failFast: false
                        )
                    }
                }

                stage('Frontend') {
                    steps {
                        runNodeLinting(
                            packageDirs: lintConfig.nodePackageDirs,
                            lintScript: 'lint',
                            failFast: false
                        )
                    }
                }

                stage('Dockerfiles') {
                    steps {
                        runHadolint(
                            dockerfiles: lintConfig.dockerfiles,
                            failFast: false
                        )
                    }
                }
            }
        }

        stage('Unit Tests') {
            steps {
                runUnitTest(
                    services: unitTestServices,
                    coverageDir: 'coverage-reports',
                    failFast: false
                )
            }
        }

        stage('Code Quality Analysis') {
            steps {
                script {
                    String branchName = env.BRANCH_NAME ?: ''
                    boolean projectLevelIssues = branchName.startsWith('feature/')
                    boolean newCodeIssues = !projectLevelIssues
                    Map issueFetchConfig = sonarConfig.fetchIssuesConfig + [:]

                    if (newCodeIssues) {
                        issueFetchConfig.inNewCodePeriod = true
                        echo "SonarQube issue fetch policy: new-code issues (${branchName ?: 'unknown branch'})"
                    } else {
                        echo "SonarQube issue fetch policy: release branch project-level issues (${branchName})"
                    }

                    runSonarQube(
                        projectKey: sonarConfig.projectKey,
                        sources: sonarConfig.sources,
                        coverageReports: sonarConfig.coverageReports,
                        fetchIssues: sonarConfig.fetchIssues,
                        fetchIssuesConfig: issueFetchConfig,
                        extraProperties: sonarConfig.extraProperties,
                        inNewCodePeriod: newCodeIssues,
                        container: 'sonar'
                    )
                }
            }
        }

        stage('Prepare Security Scanner') {
            steps {
                ensureTrivyDB()
            }
        }

        stage('Static Security Scan') {
            parallel {
                stage('Dependencies') {
                    steps {
                        runTrivyFSScan(
                            target: '.',
                            skipDirs: securityConfig.trivySkipDirs,
                            filePatterns: ['pip:requirements-.*\\.txt'],
                            includeDevDeps: true,
                            failOnVulnerabilities: true
                        )
                    }
                }

                stage('Secrets') {
                    steps {
                        runTrivySecretScan(
                            target: '.',
                            skipDirs: securityConfig.trivySkipDirs,
                            failOnSecrets: true
                        )
                    }
                }
            }
        }
    }

    post {
        always {
            cleanWs(
                deleteDirs: true,
                disableDeferredWipeout: true,
                notFailBuild: true
            )
        }
    }
}
