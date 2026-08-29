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
        testPath: '.',
        coverageThreshold: 70
    ],
    [
        name: 'todo-service',
        target: 'todo-service',
        testPath: '.',
        coverageThreshold: 70
    ]
]

def securityConfig = [
    trivyFsSkipDirs: [
        'frontend/node_modules',
        'node_modules',
        '.venv',
        '__pycache__',
        '.git',
        'coverage-reports'
    ],
    trivyImageSkipDirs: []
]

def imageSecurityConfig = [
    severities: 'HIGH,CRITICAL',
    failOnVulnerabilities: false,
    imageReportDir: 'trivy-image-reports',
    sbomOutputDir: 'sbom-reports',
    sbomFormat: 'cyclonedx',
    dependencyTrackEnabled: false,
    dependencyTrackUrl: 'http://dtrack-dependency-track-api-server.dependency-track.svc.cluster.local:8080',
    dependencyTrackCredentialsId: 'dependency-track-api-key'
]

def sonarConfig = [
    projectKey: 'homelab-app',
    abortPipeline: false,
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

def imageBuildConfig = [
    outputDir: 'image-artifacts',
    platform: 'linux/amd64',
    images: [
        [
            name: 'user-service',
            context: 'user-service',
            dockerfile: 'user-service/Dockerfile'
        ],
        [
            name: 'todo-service',
            context: 'todo-service',
            dockerfile: 'todo-service/Dockerfile'
        ],
        [
            name: 'frontend',
            context: 'frontend',
            dockerfile: 'frontend/Dockerfile'
        ]
    ]
]

pipeline {
    agent {
        kubernetes {
            yaml ciPodTemplate(images: imageBuildConfig.images)
            defaultContainer 'jnlp'
        }
    }

    options {
        buildDiscarder(logRotator(
            numToKeepStr: '10',
            artifactNumToKeepStr: '1',
            artifactDaysToKeepStr: '1'
        ))
        skipDefaultCheckout(true)
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
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
                        runRuffLinting(
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
                runUvUnitTest(
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
                    boolean projectLevelIssues = branchName.startsWith('release/')
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
                        container: 'sonar',
                        abortPipeline: sonarConfig.abortPipeline

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
                            skipDirs: securityConfig.trivyFsSkipDirs,
                            includeDevDeps: true,
                            failOnVulnerabilities: true
                        )
                    }
                }

                stage('Secrets') {
                    steps {
                        runTrivySecretScan(
                            target: '.',
                            skipDirs: securityConfig.trivyFsSkipDirs,
                            failOnSecrets: true
                        )
                    }
                }
            }
        }

        stage('Build Images') {
            when {
                expression { (env.BRANCH_NAME ?: '').startsWith('release/') }
            }
            steps {
                runReleaseImages(
                    images: imageBuildConfig.images,
                    outputDir: imageBuildConfig.outputDir,
                    platform: imageBuildConfig.platform,
                    environment: 'staging',
                    failFast: false
                )
            }
        }

        stage('Generate Image SBOM') {
            when {
                expression { (env.BRANCH_NAME ?: '').startsWith('release/') }
            }
            steps {
                runTrivySBOM(
                    imageManifest: "${imageBuildConfig.outputDir}/images.txt",
                    outputDir: imageSecurityConfig.sbomOutputDir,
                    format: imageSecurityConfig.sbomFormat,
                    uploadToDependencyTrack: imageSecurityConfig.dependencyTrackEnabled,
                    dependencyTrackUrl: imageSecurityConfig.dependencyTrackUrl,
                    dependencyTrackCredentialsId: imageSecurityConfig.dependencyTrackCredentialsId,
                    failFast: false
                )
            }
        }

        stage('Image Security Scan') {
            when {
                expression { (env.BRANCH_NAME ?: '').startsWith('release/') }
            }
            steps {
                runTrivyScan(
                    imageManifest: "${imageBuildConfig.outputDir}/images.txt",
                    outputDir: imageSecurityConfig.imageReportDir,
                    severities: imageSecurityConfig.severities,
                    failOnVulnerabilities: imageSecurityConfig.failOnVulnerabilities,
                    skipDirs: securityConfig.trivyImageSkipDirs,
                    failFast: false
                )
            }
        }

        stage('Mark Release CI Artifact') {
            when {
                expression { (env.BRANCH_NAME ?: '').startsWith('release/') }
            }
            steps {
                markReleaseCiArtifact(
                    outputDir: imageBuildConfig.outputDir
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
