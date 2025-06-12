package list.news.controller;

import list.news.service.NewsCrawlerService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/news")
public class NewsCrawlerController {

    private final NewsCrawlerService newsCrawlerService;

    @Autowired
    public NewsCrawlerController(NewsCrawlerService newsCrawlerService) {
        this.newsCrawlerService = newsCrawlerService;
    }

    @GetMapping("/popular")
    public List<String> getPopularNews() {
        return newsCrawlerService.getPopularNewsTitles();
    }

    @GetMapping("/international")
    public List<String> getInternationalNews() {
        // TODO: implement
        return List.of(); // 예시
    }

    @GetMapping("/domestic")
    public List<String> getDomesticNews() {
        // TODO: implement
        return List.of(); // 예시
    }
}
