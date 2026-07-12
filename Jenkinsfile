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
                    targets: lintConfig.pythonTargets,
                    requirementsFile: 'requirements.txt',
                    coverageDir: 'coverage-reports',
                    failFast: false
                )
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
