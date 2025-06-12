package list.news.controller;

import list.news.service.NewsService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.util.List;

@RestController
public class NewsController {

    @Autowired
    private NewsService newsService;

    @GetMapping("/api/news/latest")
    public List<String> getNewsTitles() {
        try {
            return newsService.getNewsTitles();
        } catch (IOException e) {
            e.printStackTrace();
            return List.of("뉴스를 불러오는 중 오류가 발생했습니다.");
        }
    }

    @GetMapping("/api/news/international")
    public List<String> getInternationalNewsTitles() {
        try {
            return newsService.getInternationalNewsTitles();
        } catch (IOException e) {
            e.printStackTrace();
            return List.of("국제 뉴스를 불러오는 중 오류가 발생했습니다.");
        }
    }

    @GetMapping("/api/news/domestic")
    public List<String> getDomesticNewsTitles() {
        try {
            return newsService.getDomesticNewsTitles();
        } catch (IOException e) {
            return List.of("국내 뉴스를 불러오는 중 오류 발생했습니다.");
        }
    }
}
