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
        'frontend/node_modules',
        'node_modules',
        '.venvs',
        'venv',
        '.git',
        '__pycache__',
        'coverage-reports'
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
