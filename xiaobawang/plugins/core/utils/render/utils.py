async def wait_for_all_images_in_viewport(page):
    """确保当前视口中的所有图片完全加载完成"""
    return await page.evaluate("""
    () => {
        return new Promise((resolve) => {
            const checkVisibleImagesLoaded = () => {
                const viewportHeight = window.innerHeight;
                const viewportWidth = window.innerWidth;

                const allImgs = Array.from(document.querySelectorAll('img'));
                const visibleImgs = allImgs.filter(img => {
                    const rect = img.getBoundingClientRect();
                    return (
                        rect.top >= -rect.height &&
                        rect.left >= -rect.width &&
                        rect.bottom <= viewportHeight + rect.height &&
                        rect.right <= viewportWidth + rect.width
                    );
                });

                if (visibleImgs.length === 0) {
                    return resolve('视口中没有图片');
                }

                const allLoaded = visibleImgs.every(img => {
                    return img.complete && img.naturalWidth > 0;
                });

                if (allLoaded) {
                    resolve('视口内所有图片已加载完成');
                } else {
                    setTimeout(checkVisibleImagesLoaded, 200);
                }
            };

            checkVisibleImagesLoaded();
            setTimeout(() => resolve('图片加载超时'), 10000);
        });
    }
    """)


async def scroll_and_load_all_content(page):
    """滚动页面并确保所有内容加载完成"""
    return await page.evaluate("""
    () => {
        return new Promise(async (resolve) => {
            const scrollToBottom = async () => {
                const prevHeight = document.body.scrollHeight;
                window.scrollTo(0, document.body.scrollHeight);

                await new Promise(r => setTimeout(r, 500));

                if (document.body.scrollHeight > prevHeight) {
                    await scrollToBottom();
                }
            };

            await scrollToBottom();

            window.scrollTo(0, 0);

            const viewportHeight = window.innerHeight;
            const totalHeight = document.body.scrollHeight;

            for (let i = 0; i < totalHeight; i += viewportHeight / 2) {
                window.scrollTo(0, i);
                await new Promise(r => setTimeout(r, 200));
            }

            window.scrollTo(0, 0);

            resolve('所有内容已加载');
        });
    }
    """)


async def get_element_dimensions(page, selector):
    """
    获取页面元素的位置和尺寸

    Args:
        page: 浏览器页面对象
        selector: 元素选择器

    Returns:
        dict: 包含元素的位置和尺寸信息，如果找不到元素则返回None
    """
    element_handle = await page.wait_for_selector(selector)
    if element_handle is None:
        return None

    bounding_box = await element_handle.bounding_box()
    if not bounding_box:
        return None

    return bounding_box


async def expand_scrollable_containers(page):
    """
    展开所有可滚动容器，使其完整显示所有内容

    Args:
        page: 浏览器页面对象
    """
    await page.evaluate("""
    () => {
        const scrollContainers = Array.from(document.querySelectorAll('.compact-teams, .battle-report-involved'));
        scrollContainers.forEach(container => {
            if (container.scrollHeight > container.clientHeight) {
                container.style.height = 'auto';
                container.style.maxHeight = 'none';
                container.style.overflow = 'visible';
            }
        });
    }
    """)


async def get_teams_count(page):
    """
    获取战斗报告中的队伍数量

    Args:
        page: 浏览器页面对象

    Returns:
        int: 队伍数量
    """
    return await page.evaluate("""
    () => {
        const teamsContainer = document.querySelector('.compact-teams');
        if (!teamsContainer) {
            return 2;
        }

        const teamCards = teamsContainer.querySelectorAll('.compact-team-card');
        return teamCards.length;
    }
    """)
